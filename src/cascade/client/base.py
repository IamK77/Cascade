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

"""Client base — transaction infrastructure and corruption recovery."""

from __future__ import annotations

import subprocess
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from cascade.core.cascade import Cascade
from cascade.core.node import Node
from cascade.errors import StorageCorruptionError
from cascade.events import EventType
from cascade.replay import replay as replay_events
from cascade.storage.file_storage import FileStorage
from cascade.storage.protocol import StorageProtocol
from cascade.types import (
    Context,
    Result,
)


class _Tx:
    """Mutation transaction — holds graph, handles emit/save/op_id."""

    def __init__(self, graph: Cascade, storage: StorageProtocol, op_id: str | None):
        self.graph = graph
        self._storage = storage
        self._op_id = op_id
        self._dirty = False
        self._trace_id = uuid.uuid4().hex

    def emit(self, event_type: EventType, **data: Any) -> None:
        self._storage.events.emit(
            event_type,
            logical_ts=self._storage.next_lamport(),
            trace_id=self._trace_id,
            **data,
        )
        self._dirty = True

    def save(self) -> None:
        self._storage.save(self.graph)

    def ok(self, result: Result) -> Result:
        """Finalize a successful mutation: save graph, record op, return result."""
        if self._dirty:
            self._storage.save(self.graph)
        if self._op_id is not None:
            self._storage.ops.record(self._op_id, result.to_dict())
        return result


class ClientBase:
    """Transaction infrastructure shared by all client mixins."""

    def __init__(self, storage: StorageProtocol | str | Path = ".cascade"):
        if isinstance(storage, (str, Path)):
            self._storage: StorageProtocol = FileStorage(storage)
        else:
            self._storage = storage

    def _cached_op(self, op_id: str | None) -> Result | None:
        """Return cached result for a previously executed op_id."""
        if op_id is None:
            return None
        cached = self._storage.ops.get(op_id)
        if cached is not None:
            return Result.from_dict(cached)
        return None

    def recover_from_corruption(self, error: StorageCorruptionError) -> Cascade:
        """Recover graph from event log after detecting storage corruption.

        1. Preserve the corrupt snapshot for forensics
        2. Replay the event log (source of truth) to rebuild the graph
        3. Save the recovered graph (self-heal the snapshot)
        4. Record the corruption event in the audit trail

        If the event log is also unreadable, starts from an empty graph.
        """
        try:
            backup_path = self._storage.backup_corrupt()
        except OSError:
            backup_path = None

        try:
            events = self._storage.events.read_all()
        except Exception:
            events = []

        if events:
            graph = replay_events(events, self._storage.content)
            recovery_source = "event_log"
        else:
            graph = Cascade()
            recovery_source = "empty"

        self._storage.save(graph)

        try:
            self._storage.events.emit(
                EventType.GRAPH_CORRUPTED,
                logical_ts=self._storage.next_lamport(),
                reason=error.reason,
                recovery_source=recovery_source,
                node_count=len(graph.nodes),
                backup_path=backup_path,
            )
        except Exception:
            pass

        return graph

    def _load_or_recover(self) -> Cascade:
        """Load graph, recovering from corruption. Caller must hold lock."""
        try:
            return self._storage.load() or Cascade()
        except StorageCorruptionError as e:
            return self.recover_from_corruption(e)

    def load(self) -> Cascade:
        """Load graph with automatic corruption recovery.

        Returns the current graph, or an empty Cascade if no data exists.
        If the snapshot is corrupt, recovers from the event log transparently.
        """
        with self._storage.lock():
            return self._load_or_recover()

    @contextmanager
    def _mutate(self, op_id: str | None = None) -> Generator[_Tx, None, None]:
        """Transaction context: lock, load, yield _Tx."""
        with self._storage.lock():
            graph = self._load_or_recover()
            yield _Tx(graph, self._storage, op_id)

    @property
    def storage(self) -> StorageProtocol:
        return self._storage


# ---------------------------------------------------------------------------
# Module-private helpers
# ---------------------------------------------------------------------------


def _get_git_ref() -> str:
    """Get current HEAD commit hash, or empty string if not in a git repo."""
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode == 0:
            return r.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return ""


def _update_context(
    node: Node,
    *,
    summary: str = "",
    critical: dict[str, Any] | None = None,
    artifacts: str = "",
    merge_mode: str = "merge",
) -> bool:
    """Update node context based on params. Returns True if context was updated."""
    if critical is None and not summary and not artifacts:
        return False

    if node.context is None:
        node.context = Context()

    ctx = node.context

    if merge_mode == "replace":
        if critical is not None:
            ctx.critical = dict(critical)
        if summary:
            ctx.summary = summary
        if artifacts:
            ctx.artifacts = str(artifacts)
    elif merge_mode == "append":
        if critical is not None:
            ctx.critical.update(critical)
        if summary:
            ctx.summary = (ctx.summary + "\n" + summary).strip()
        if artifacts:
            ctx.artifacts = str(artifacts)
    else:  # merge (default)
        if critical is not None:
            ctx.critical.update(critical)
        if summary:
            if ctx.summary:
                ctx.summary = ctx.summary + "\n" + summary
            else:
                ctx.summary = summary
        if artifacts:
            ctx.artifacts = str(artifacts)

    return True
