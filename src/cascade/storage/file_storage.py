# Copyright 2026 Hangzhou Autoseek Information Technology Co., Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Storage for Cascade persistence."""

import json
import os
import threading
import time
from collections.abc import Generator
from contextlib import contextmanager
from enum import Enum
from pathlib import Path

from filelock import FileLock, Timeout

from cascade.core.cascade import Cascade
from cascade.errors import LockError, StorageCorruptionError
from cascade.events import FileEventStore
from cascade.storage._serde import deserialize_graph, serialize_graph
from cascade.storage.content import ContentStore, LocalContentStore
from cascade.storage.op_log import FileOpLog
from cascade.storage.protocol import EventStoreProtocol, OpLogProtocol, TokenStoreProtocol
from cascade.storage.token_store import FileTokenStore


class StorageScope(Enum):
    """Storage scope for graph persistence."""

    PROJECT = "project"
    USER = "user"


class FileStorage:
    """Handles persistence of Cascade structures with file locking.

    Storage structure:
        base_dir/
            graph.json        # Graph structure (nodes, edges, states)
            .lock             # Lock file for concurrent access
            artifacts/
                <node_id>.md  # Artifacts content per node
    """

    def __init__(
        self,
        base_dir: Path | str | None = None,
        scope: StorageScope = StorageScope.PROJECT,
        content: ContentStore | None = None,
    ):
        if base_dir is not None:
            self.base_dir = Path(base_dir)
        elif scope == StorageScope.USER:
            self.base_dir = Path.home() / ".cascade"
        else:
            self.base_dir = Path.cwd() / ".cascade"

        self._file_lock = FileLock(self.base_dir / ".lock")
        self._thread_lock = threading.Lock()
        self._lamport: int = self._recover_lamport()
        self.events: EventStoreProtocol = FileEventStore(self.base_dir)
        self.tokens: TokenStoreProtocol = FileTokenStore(self.base_dir)
        self.ops: OpLogProtocol = FileOpLog(self.base_dir)
        self.content = content or LocalContentStore(self.base_dir)

    def _recover_lamport(self) -> int:
        """Read lamport/HLC from graph.json at startup."""
        graph_path = self.base_dir / "graph.json"
        if not graph_path.exists():
            return 0
        try:
            data = json.loads(graph_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return 0
            return int(data.get("lamport", 0))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError, ValueError):
            return 0

    def next_lamport(self) -> int:
        """Hybrid Logical Clock: max(physical_time_ms, last) + 1.

        Backward compatible with pure Lamport — still a monotonically
        increasing integer. But values now embed physical time, enabling
        causal ordering across distributed instances.
        """
        physical_ms = int(time.time() * 1000)
        self._lamport = max(physical_ms, self._lamport) + 1
        return self._lamport

    def observe(self, remote_ts: int) -> None:
        """Advance HLC past a remote timestamp."""
        self._lamport = max(self._lamport, remote_ts)

    @classmethod
    def project(cls, base_dir: Path | str | None = None) -> "FileStorage":
        return cls(base_dir=base_dir, scope=StorageScope.PROJECT)

    @classmethod
    def user(cls) -> "FileStorage":
        return cls(scope=StorageScope.USER)

    def exists(self) -> bool:
        return (self.base_dir / "graph.json").exists()

    @contextmanager
    def lock(self, timeout: float = 10.0, blocking: bool = True) -> Generator[None, None, None]:
        """Acquire lock for atomic operations.

        Two layers: threading.Lock for intra-process safety (multiple
        threads in one process), FileLock for inter-process safety
        (multiple processes accessing the same .cascade/ directory).
        """
        acquired = self._thread_lock.acquire(timeout=timeout if blocking else 0)
        if not acquired:
            raise LockError(
                "Could not acquire lock: another thread holds it"
                if not blocking
                else f"Could not acquire thread lock within {timeout} seconds"
            )
        try:
            self.base_dir.mkdir(parents=True, exist_ok=True)
            with self._file_lock.acquire(timeout=timeout if blocking else 0):
                yield
        except Timeout:
            raise LockError(
                f"Could not acquire lock within {timeout} seconds"
                if blocking
                else "Could not acquire lock: another process holds it"
            )
        finally:
            self._thread_lock.release()

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def save(self, cascade: Cascade) -> None:
        """Save the Cascade to storage."""
        self.base_dir.mkdir(parents=True, exist_ok=True)
        graph_data = serialize_graph(cascade, self._lamport, self.content)
        graph_path = self.base_dir / "graph.json"
        self._atomic_write(graph_path, json.dumps(graph_data, indent=2, ensure_ascii=False))

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        """Write content atomically via tmp file + rename.

        Concurrent readers (e.g. cascade watch) see either the old or
        new file complete — never a torn write.
        """
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, path)

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    def load(self) -> Cascade | None:
        """Load Cascade from storage.

        Returns None if no data exists. Raises StorageCorruptionError
        if the file exists but cannot be deserialized — the caller
        must decide recovery strategy.
        """
        graph_path = self.base_dir / "graph.json"
        if not graph_path.exists():
            return None

        try:
            raw = graph_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as e:
            raise StorageCorruptionError(
                "binary content in graph.json",
                path=str(graph_path),
            ) from e

        if not raw.strip():
            raise StorageCorruptionError(
                "empty graph.json",
                path=str(graph_path),
            )

        try:
            graph_data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise StorageCorruptionError(
                "malformed JSON in graph.json",
                path=str(graph_path),
            ) from e

        if not isinstance(graph_data, dict):
            raise StorageCorruptionError(
                f"expected JSON object, got {type(graph_data).__name__}",
                path=str(graph_path),
            )

        try:
            cascade, self._lamport = deserialize_graph(graph_data, self.content)
            return cascade
        except (KeyError, AttributeError, TypeError, ValueError) as e:
            raise StorageCorruptionError(
                f"invalid graph structure: {e}",
                path=str(graph_path),
            ) from e

    def backup_corrupt(self) -> str | None:
        """Rename corrupt graph.json for forensic preservation.

        Returns the backup path as string, or None if no file to back up.
        """
        graph_path = self.base_dir / "graph.json"
        if not graph_path.exists():
            return None
        backup_path = self.base_dir / f"graph.json.corrupt.{time.time_ns()}"
        graph_path.rename(backup_path)
        return str(backup_path)

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------

    def delete(self) -> None:
        """Delete all saved data."""
        import shutil

        if self.base_dir.exists():
            shutil.rmtree(self.base_dir)
