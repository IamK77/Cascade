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

"""Event sourcing — append-only log of all graph mutations.

Every significant action is recorded as an event. The event log
lives alongside the graph state as .cascade/events.jsonl (one JSON
object per line). It provides:

- Audit trail: who did what when
- Time travel: reconstruct what the graph looked like at any point
- Debugging: replay events to reproduce issues
"""

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class EventType(Enum):
    """All event types in the system."""

    NODE_ADDED = "node_added"
    NODE_REMOVED = "node_removed"
    EDGE_ADDED = "edge_added"
    EDGE_REMOVED = "edge_removed"
    TASK_CLAIMED = "task_claimed"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    TASK_RELEASED = "task_released"
    TASK_TIMED_OUT = "task_timed_out"
    REWORK_REQUESTED = "rework_requested"
    NODE_EDITED = "node_edited"
    NODE_SPLIT = "node_split"
    NODE_REFINED = "node_refined"
    NODE_CANCELLED = "node_cancelled"


def _compute_hash(event_dict: dict[str, Any], prev_hash: str) -> str:
    """Compute SHA-256 hash of event content chained with prev_hash."""
    canonical = json.dumps(event_dict, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256((canonical + prev_hash).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Event:
    """A single event in the log.

    Immutable record of something that happened to the graph.
    hash and prev_hash form a verifiable chain — tampering with
    any event breaks all subsequent hashes.
    """

    type: EventType
    timestamp: float
    id: str = ""
    logical_ts: int = 0
    data: dict[str, Any] = field(default_factory=dict)
    trace_id: str = ""
    prev_hash: str = ""
    hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "type": self.type.value,
            "timestamp": self.timestamp,
            "logical_ts": self.logical_ts,
            "data": self.data,
        }
        if self.trace_id:
            d["trace_id"] = self.trace_id
        if self.prev_hash:
            d["prev_hash"] = self.prev_hash
        if self.hash:
            d["hash"] = self.hash
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Event":
        return cls(
            type=EventType(d["type"]),
            timestamp=d["timestamp"],
            id=d.get("id", ""),
            logical_ts=d.get("logical_ts", 0),
            data=d.get("data", {}),
            trace_id=d.get("trace_id", ""),
            prev_hash=d.get("prev_hash", ""),
            hash=d.get("hash", ""),
        )


class FileEventStore:
    """Append-only event log backed by JSONL file.

    Core methods (emit, read_all, clear, count, verify_chain) are
    file-specific. Query methods (read_by_node, read_range, etc.)
    are provided by EventStoreQueries and delegate to read_all().
    """

    def __init__(self, base_dir: Path | str):
        self._path = Path(base_dir) / "events.jsonl"
        self._last_hash: str = self._recover_last_hash()

    def _recover_last_hash(self) -> str:
        if not self._path.exists():
            return ""
        last_hash = ""
        with open(self._path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    last_hash = json.loads(line).get("hash", "")
        return last_hash

    def append(self, event: Event) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")

    def emit(
        self, event_type: EventType, logical_ts: int, *, trace_id: str = "", **data: Any
    ) -> Event:
        event_id = uuid.uuid4().hex
        timestamp = time.time()
        content: dict[str, Any] = {
            "id": event_id,
            "type": event_type.value,
            "timestamp": timestamp,
            "logical_ts": logical_ts,
            "data": data,
        }
        if trace_id:
            content["trace_id"] = trace_id
        event_hash = _compute_hash(content, self._last_hash)
        event = Event(
            type=event_type,
            timestamp=timestamp,
            id=event_id,
            logical_ts=logical_ts,
            data=data,
            trace_id=trace_id,
            prev_hash=self._last_hash,
            hash=event_hash,
        )
        self.append(event)
        self._last_hash = event_hash
        return event

    def read_all(self) -> list[Event]:
        if not self._path.exists():
            return []
        events = []
        with open(self._path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(Event.from_dict(json.loads(line)))
                except (json.JSONDecodeError, KeyError):
                    continue
        return events

    def clear(self) -> None:
        if self._path.exists():
            self._path.unlink()
        self._last_hash = ""

    @property
    def count(self) -> int:
        if not self._path.exists():
            return 0
        with open(self._path, encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())

    def verify_chain(self) -> tuple[bool, str]:
        events = self.read_all()
        prev_hash = ""
        for i, event in enumerate(events):
            if not event.hash:
                continue
            if event.prev_hash != prev_hash:
                return False, (
                    f"Event #{i} (logical_ts={event.logical_ts}): "
                    f"prev_hash mismatch — expected {prev_hash[:12]}..., "
                    f"got {event.prev_hash[:12]}..."
                )
            content: dict[str, Any] = {
                "id": event.id,
                "type": event.type.value,
                "timestamp": event.timestamp,
                "logical_ts": event.logical_ts,
                "data": event.data,
            }
            if event.trace_id:
                content["trace_id"] = event.trace_id
            expected = _compute_hash(content, prev_hash)
            if event.hash != expected:
                return False, (
                    f"Event #{i} (logical_ts={event.logical_ts}): "
                    f"hash mismatch — content was tampered"
                )
            prev_hash = event.hash
        return True, ""

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
