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
from collections.abc import Generator
from contextlib import contextmanager
from enum import Enum
from pathlib import Path
from typing import Any

from filelock import FileLock, Timeout

from cascade.core.cascade import Cascade
from cascade.core.node import Node
from cascade.core.state import NodeState
from cascade.events import EventStore
from cascade.storage.token_store import TokenStore
from cascade.types import Context, Contract


class StorageScope(Enum):
    """Storage scope for graph persistence."""

    PROJECT = "project"
    USER = "user"


class LockError(Exception):
    """Raised when lock cannot be acquired."""


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
    ):
        if base_dir is not None:
            self.base_dir = Path(base_dir)
        elif scope == StorageScope.USER:
            self.base_dir = Path.home() / ".cascade"
        else:
            self.base_dir = Path.cwd() / ".cascade"

        self.artifacts_dir = self.base_dir / "artifacts"
        self._file_lock = FileLock(self.base_dir / ".lock")
        self._thread_lock = threading.Lock()
        self.events = EventStore(self.base_dir)
        self.tokens = TokenStore(self.base_dir)

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
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

        graph_data: dict[str, Any] = {
            "epoch": cascade.epoch,
            "nodes": {},
            "edges": [],
            "agent_tasks": {},
        }

        for node_id, node in cascade.nodes.items():
            node_data: dict[str, Any] = {
                "id": node.id,
                "state": node.state.name,
            }

            if node.agent_id:
                node_data["agent_id"] = node.agent_id
                if node.state == NodeState.ACTIVE:
                    graph_data["agent_tasks"][node.agent_id] = node_id

            if node.claimed_at is not None:
                node_data["claimed_at"] = node.claimed_at
            if node.timeout is not None:
                node_data["timeout"] = node.timeout

            if node.context:
                ctx_data: dict[str, Any] = {}
                if node.context.critical:
                    ctx_data["critical"] = node.context.critical
                if node.context.summary:
                    ctx_data["summary"] = node.context.summary
                if node.context.artifacts:
                    # Always save non-empty artifacts to file — no heuristic.
                    artifacts_path = self._save_artifacts(node_id, node.context.artifacts)
                    ctx_data["artifacts"] = artifacts_path
                if ctx_data:
                    node_data["context"] = ctx_data

            graph_data["nodes"][node_id] = node_data

        # Save edges with contracts
        for (from_id, to_id), contract in cascade._contracts.items():
            edge_data: dict[str, str] = {
                "from": from_id,
                "to": to_id,
                "expectation": contract.expectation,
                "promise": contract.promise,
            }
            graph_data["edges"].append(edge_data)

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

    def save_node(self, cascade: Cascade, node_id: str) -> None:
        """Save a single node incrementally."""
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

        graph_path = self.base_dir / "graph.json"
        if graph_path.exists():
            graph_data = json.loads(graph_path.read_text(encoding="utf-8"))
        else:
            graph_data = {"nodes": {}, "edges": []}

        node = cascade.nodes.get(node_id)
        if not node:
            return

        node_data: dict[str, Any] = {
            "id": node.id,
            "state": node.state.name,
        }

        if node.agent_id:
            node_data["agent_id"] = node.agent_id

        if node.context:
            ctx_data: dict[str, Any] = {}
            if node.context.critical:
                ctx_data["critical"] = node.context.critical
            if node.context.summary:
                ctx_data["summary"] = node.context.summary
            if node.context.artifacts:
                artifacts_path = self._save_artifacts(node_id, node.context.artifacts)
                ctx_data["artifacts"] = artifacts_path
            if ctx_data:
                node_data["context"] = ctx_data

        graph_data["nodes"][node_id] = node_data
        self._atomic_write(graph_path, json.dumps(graph_data, indent=2, ensure_ascii=False))

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    def load(self) -> Cascade | None:
        """Load Cascade from storage."""
        graph_path = self.base_dir / "graph.json"
        if not graph_path.exists():
            return None

        try:
            graph_data = json.loads(graph_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

        cascade = Cascade()
        cascade.epoch = graph_data.get("epoch", 0)

        # Load nodes
        for node_id, node_data in graph_data.get("nodes", {}).items():
            state = NodeState[node_data.get("state", "PENDING")]
            agent_id = node_data.get("agent_id")

            context = None
            if "context" in node_data:
                ctx_data = node_data["context"]
                artifacts = ctx_data.get("artifacts", "")

                # Load artifacts from file if it's a path reference
                if artifacts.startswith(".cascade/artifacts/"):
                    filename = artifacts.replace(".cascade/artifacts/", "")
                    artifacts_path = self.base_dir / "artifacts" / filename
                    if artifacts_path.exists():
                        artifacts = artifacts_path.read_text(encoding="utf-8")
                    else:
                        artifacts = ""

                context = Context(
                    critical=ctx_data.get("critical", {}),
                    summary=ctx_data.get("summary", ""),
                    artifacts=artifacts,
                )

            node = Node(
                id=node_id,
                state=state,
                context=context,
                agent_id=agent_id,
                claimed_at=node_data.get("claimed_at"),
                timeout=node_data.get("timeout"),
            )
            cascade.add_node(node)

        # Load edges via _restore_edge — skips cycle detection but
        # recomputes readiness, so PENDING/READY states are always
        # derived from the graph rather than blindly trusted from JSON.
        for edge in graph_data.get("edges", []):
            from_id = edge.get("from")
            to_id = edge.get("to")
            expectation = edge.get("expectation", "")
            promise = edge.get("promise", "")

            if from_id in cascade.nodes and to_id in cascade.nodes:
                cascade._restore_edge(
                    from_id,
                    to_id,
                    Contract(expectation=expectation, promise=promise),
                )

        return cascade

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------

    def delete(self) -> None:
        """Delete all saved data."""
        import shutil

        if self.base_dir.exists():
            shutil.rmtree(self.base_dir)

    def _save_artifacts(self, node_id: str, content: str) -> str:
        """Save artifacts content to file. Returns the relative path."""
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        artifacts_path = self.artifacts_dir / f"{node_id}.md"
        artifacts_path.write_text(content, encoding="utf-8")
        return f".cascade/artifacts/{node_id}.md"
