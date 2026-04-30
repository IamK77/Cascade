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


@dataclass(frozen=True)
class Event:
    """A single event in the log.

    Immutable record of something that happened to the graph.
    """

    type: EventType
    timestamp: float
    id: str = ""
    logical_ts: int = 0
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "timestamp": self.timestamp,
            "logical_ts": self.logical_ts,
            "data": self.data,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Event":
        return cls(
            type=EventType(d["type"]),
            timestamp=d["timestamp"],
            id=d.get("id", ""),
            logical_ts=d.get("logical_ts", 0),
            data=d.get("data", {}),
        )


class EventStore:
    """Append-only event log backed by JSONL file.

    Events are appended one per line. Reading loads all events.
    The store is designed to be used alongside FileStorage.

    Maintains a Lamport clock: each emit increments the counter.
    Call ``observe(logical_ts)`` when receiving events from another
    store to advance the clock past the observed timestamp.
    """

    def __init__(self, base_dir: Path | str):
        self._path = Path(base_dir) / "events.jsonl"
        self._lamport: int = self._recover_lamport()

    def _recover_lamport(self) -> int:
        """Read the last event's logical_ts to resume the counter across restarts."""
        if not self._path.exists():
            return 0
        last_line = ""
        try:
            with open(self._path, "rb") as f:
                f.seek(0, 2)
                pos = f.tell()
                while pos > 0:
                    pos -= 1
                    f.seek(pos)
                    ch = f.read(1)
                    if ch == b"\n" and last_line:
                        break
                    last_line = ch.decode() + last_line
        except OSError:
            return 0
        last_line = last_line.strip()
        if not last_line:
            return 0
        try:
            return int(json.loads(last_line).get("logical_ts", 0))
        except (json.JSONDecodeError, ValueError):
            return 0

    def observe(self, remote_ts: int) -> None:
        """Advance clock to at least ``remote_ts`` (Lamport rule on receive)."""
        if remote_ts > self._lamport:
            self._lamport = remote_ts

    def append(self, event: Event) -> None:
        """Append an event to the log."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")

    def emit(self, event_type: EventType, **data: Any) -> Event:
        """Create, append, and return an event in one call."""
        self._lamport += 1
        event = Event(
            type=event_type,
            timestamp=time.time(),
            id=uuid.uuid4().hex,
            logical_ts=self._lamport,
            data=data,
        )
        self.append(event)
        return event

    def read_all(self) -> list[Event]:
        """Read all events from the log."""
        if not self._path.exists():
            return []
        events = []
        with open(self._path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    events.append(Event.from_dict(json.loads(line)))
        return events

    def read_since(self, since: float) -> list[Event]:
        """Read events after a given timestamp."""
        return [e for e in self.read_all() if e.timestamp > since]

    def read_by_type(self, event_type: EventType) -> list[Event]:
        """Read events of a specific type."""
        return [e for e in self.read_all() if e.type == event_type]

    def read_by_node(self, node_id: str) -> list[Event]:
        """Read events related to a specific node."""
        return [
            e
            for e in self.read_all()
            if e.data.get("node_id") == node_id
            or e.data.get("source_node_id") == node_id
            or e.data.get("corrective_node_id") == node_id
            or node_id in e.data.get("new_node_ids", [])
        ]

    def clear(self) -> None:
        """Clear all events (for testing)."""
        if self._path.exists():
            self._path.unlink()

    @property
    def count(self) -> int:
        """Number of events in the log."""
        if not self._path.exists():
            return 0
        with open(self._path, encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())

    def summary(self) -> dict[str, int]:
        """Count events by type."""
        counts: dict[str, int] = {}
        for event in self.read_all():
            key = event.type.value
            counts[key] = counts.get(key, 0) + 1
        return counts
