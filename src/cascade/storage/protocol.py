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

"""Storage protocols — interfaces any Cascade backend must implement.

Each sub-component (events, tokens, ops, content) is a protocol.
FileStorage provides file-based implementations; distributed backends
(Postgres, Redis) provide their own.
"""

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any, Protocol, runtime_checkable

from cascade.core.cascade import Cascade
from cascade.events import Event, EventType
from cascade.storage.content import ContentStore
from cascade.storage.token_store import CancelNotifier
from cascade.types import TokenStatus

# ---------------------------------------------------------------------------
# Sub-component protocols
# ---------------------------------------------------------------------------


@runtime_checkable
class EventStoreProtocol(Protocol):
    """Append-only event log with query methods.

    Core methods (emit, read_all, clear, count, verify_chain) must be
    implemented by every backend. Query methods have default implementations
    in EventStoreQueries that delegate to read_all() — remote backends
    can inherit those or override with native queries.
    """

    def emit(
        self, event_type: EventType, logical_ts: int, *, trace_id: str = "", **data: Any
    ) -> Event: ...

    def read_all(self) -> list[Event]: ...

    def read_since(self, since: float) -> list[Event]: ...

    def read_at(self, logical_ts: int) -> Event | None: ...

    def read_range(self, from_ts: int, to_ts: int) -> list[Event]: ...

    def read_until(self, until_ts: int) -> list[Event]: ...

    def read_by_type(self, event_type: EventType) -> list[Event]: ...

    def read_by_trace(self, trace_id: str) -> list[Event]: ...

    def read_by_node(self, node_id: str) -> list[Event]: ...

    def summary(self) -> dict[str, int]: ...

    def clear(self) -> None: ...

    @property
    def count(self) -> int: ...

    def verify_chain(self) -> tuple[bool, str]: ...


@runtime_checkable
class TokenStoreProtocol(Protocol):
    """Task claim token storage."""

    def create(
        self,
        node_id: str,
        agent_id: str,
        claimed_at: float,
        notifier: "CancelNotifier | None" = None,
    ) -> TokenStatus: ...

    def check(self, node_id: str) -> TokenStatus | None: ...

    def invalidate(self, node_id: str, reason: str) -> TokenStatus | None: ...

    def cleanup(self, node_id: str) -> None: ...


@runtime_checkable
class OpLogProtocol(Protocol):
    """Idempotent operation log."""

    def get(self, op_id: str) -> dict[str, Any] | None: ...

    def record(self, op_id: str, result: dict[str, Any]) -> None: ...


# ---------------------------------------------------------------------------
# Event query mixin — convenience methods built on read_all()
# ---------------------------------------------------------------------------


class EventStoreQueries:
    """Query methods any EventStore gets for free.

    Subclass this alongside your EventStore implementation, or use
    it standalone. All methods delegate to self.read_all().
    """

    def read_all(self) -> list[Event]:
        raise NotImplementedError

    def read_since(self, since: float) -> list[Event]:
        return [e for e in self.read_all() if e.timestamp > since]

    def read_at(self, logical_ts: int) -> Event | None:
        for e in self.read_all():
            if e.logical_ts == logical_ts:
                return e
        return None

    def read_range(self, from_ts: int, to_ts: int) -> list[Event]:
        return [e for e in self.read_all() if from_ts <= e.logical_ts <= to_ts]

    def read_until(self, until_ts: int) -> list[Event]:
        return [e for e in self.read_all() if e.logical_ts <= until_ts]

    def read_by_type(self, event_type: EventType) -> list[Event]:
        return [e for e in self.read_all() if e.type == event_type]

    def read_by_trace(self, trace_id: str) -> list[Event]:
        return [e for e in self.read_all() if e.trace_id == trace_id]

    def read_by_node(self, node_id: str) -> list[Event]:
        return [
            e
            for e in self.read_all()
            if e.data.get("node_id") == node_id
            or e.data.get("source_node_id") == node_id
            or e.data.get("corrective_node_id") == node_id
            or node_id in e.data.get("new_node_ids", [])
        ]

    def summary(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for event in self.read_all():
            key = event.type.value
            counts[key] = counts.get(key, 0) + 1
        return counts


# ---------------------------------------------------------------------------
# Top-level storage protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class StorageProtocol(Protocol):
    """Interface for Cascade persistence backends.

    FileStorage is the built-in implementation (JSON + filelock).
    Distributed backends (Postgres, Redis, etc.) implement this
    same protocol.
    """

    events: EventStoreProtocol
    tokens: TokenStoreProtocol
    ops: OpLogProtocol
    content: ContentStore

    def exists(self) -> bool: ...

    def next_lamport(self) -> int: ...

    def observe(self, remote_ts: int) -> None: ...

    @contextmanager
    def lock(self, timeout: float = 10.0, blocking: bool = True) -> Generator[None, None, None]: ...

    def load(self) -> Cascade | None: ...

    def save(self, cascade: Cascade) -> None: ...

    def backup_corrupt(self, reason: str) -> str | None: ...

    def delete(self) -> None: ...
