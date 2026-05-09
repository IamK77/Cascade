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

"""Unit tests for src/cascade/events.py — query methods and verify_chain edge cases."""

import json
import time
from pathlib import Path

import pytest

from cascade.events import Event, EventType, FileEventStore, _compute_hash

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path: Path) -> FileEventStore:
    """Create a FileEventStore backed by a temporary directory."""
    return FileEventStore(tmp_path)


@pytest.fixture
def populated_store(store: FileEventStore) -> FileEventStore:
    """A store pre-loaded with a diverse set of events."""
    store.emit(EventType.NODE_ADDED, logical_ts=1, node_id="a")
    store.emit(EventType.NODE_ADDED, logical_ts=2, node_id="b")
    store.emit(
        EventType.EDGE_ADDED,
        logical_ts=3,
        node_id="a",
        target="b",
    )
    store.emit(
        EventType.TASK_CLAIMED,
        logical_ts=4,
        node_id="a",
        agent_id="agent-1",
        trace_id="trace-001",
    )
    store.emit(
        EventType.TASK_COMPLETED,
        logical_ts=5,
        node_id="a",
        trace_id="trace-001",
    )
    store.emit(
        EventType.TASK_CLAIMED,
        logical_ts=6,
        node_id="b",
        agent_id="agent-2",
        trace_id="trace-002",
    )
    return store


# ===========================================================================
# Event / EventType basics
# ===========================================================================


class TestEventType:
    """Verify EventType enum members."""

    def test_all_event_types(self):
        assert len(EventType) == 15

    def test_roundtrip_value(self):
        for et in EventType:
            assert EventType(et.value) is et


class TestEvent:
    """Event dataclass serialization."""

    def test_to_dict_excludes_empty_optional_fields(self):
        e = Event(type=EventType.NODE_ADDED, timestamp=1.0, id="abc", logical_ts=0)
        d = e.to_dict()
        assert "trace_id" not in d
        assert "prev_hash" not in d
        assert "hash" not in d

    def test_to_dict_includes_non_empty_optional_fields(self):
        e = Event(
            type=EventType.NODE_ADDED,
            timestamp=1.0,
            id="abc",
            logical_ts=0,
            trace_id="t1",
            prev_hash="ph",
            hash="h",
        )
        d = e.to_dict()
        assert d["trace_id"] == "t1"
        assert d["prev_hash"] == "ph"
        assert d["hash"] == "h"

    def test_from_dict_minimal(self):
        d = {"type": "node_added", "timestamp": 1.0}
        e = Event.from_dict(d)
        assert e.type == EventType.NODE_ADDED
        assert e.id == ""
        assert e.logical_ts == 0
        assert e.data == {}
        assert e.trace_id == ""

    def test_roundtrip(self):
        e = Event(
            type=EventType.REWORK_REQUESTED,
            timestamp=99.9,
            id="xyz",
            logical_ts=7,
            data={"reason": "bad"},
            trace_id="t42",
            prev_hash="aaa",
            hash="bbb",
        )
        assert Event.from_dict(e.to_dict()) == e

    def test_from_dict_invalid_type_raises(self):
        with pytest.raises(ValueError):
            Event.from_dict({"type": "nonexistent_type", "timestamp": 0})


# ===========================================================================
# _compute_hash
# ===========================================================================


class TestComputeHash:
    def test_deterministic(self):
        d = {"a": 1, "b": 2}
        assert _compute_hash(d, "prev") == _compute_hash(d, "prev")

    def test_different_prev_different_hash(self):
        d = {"a": 1}
        assert _compute_hash(d, "x") != _compute_hash(d, "y")

    def test_key_order_irrelevant(self):
        d1 = {"b": 2, "a": 1}
        d2 = {"a": 1, "b": 2}
        assert _compute_hash(d1, "") == _compute_hash(d2, "")


# ===========================================================================
# FileEventStore — core methods
# ===========================================================================


class TestFileEventStoreCore:
    """Tests for emit, read_all, clear, count, append."""

    def test_emit_returns_event(self, store: FileEventStore):
        e = store.emit(EventType.NODE_ADDED, logical_ts=0, node_id="x")
        assert e.type == EventType.NODE_ADDED
        assert e.data["node_id"] == "x"
        assert e.hash != ""
        assert e.id != ""

    def test_emit_chains_hashes(self, store: FileEventStore):
        e1 = store.emit(EventType.NODE_ADDED, logical_ts=0, node_id="a")
        e2 = store.emit(EventType.NODE_ADDED, logical_ts=1, node_id="b")
        assert e2.prev_hash == e1.hash

    def test_read_all_empty_no_file(self, tmp_path: Path):
        """read_all returns [] when the events file doesn't exist."""
        s = FileEventStore(tmp_path / "nonexistent_subdir")
        assert s.read_all() == []

    def test_clear(self, store: FileEventStore):
        store.emit(EventType.NODE_ADDED, logical_ts=0, node_id="x")
        assert store.count == 1
        store.clear()
        assert store.count == 0
        assert store.read_all() == []

    def test_count_empty(self, store: FileEventStore):
        assert store.count == 0

    def test_count_increments(self, store: FileEventStore):
        for i in range(5):
            store.emit(EventType.NODE_ADDED, logical_ts=i, node_id=f"n{i}")
        assert store.count == 5

    def test_read_all_skips_blank_lines(self, store: FileEventStore):
        """Blank lines in the JSONL file are silently skipped."""
        store.emit(EventType.NODE_ADDED, logical_ts=0, node_id="a")
        # Inject a blank line
        with open(store._path, "a", encoding="utf-8") as f:
            f.write("\n\n")
        assert len(store.read_all()) == 1

    def test_read_all_skips_corrupt_json(self, store: FileEventStore):
        """Malformed JSON lines are silently skipped."""
        store.emit(EventType.NODE_ADDED, logical_ts=0, node_id="a")
        with open(store._path, "a", encoding="utf-8") as f:
            f.write("{bad json!!!\n")
        assert len(store.read_all()) == 1

    def test_read_all_skips_missing_key(self, store: FileEventStore):
        """JSON objects missing required keys are skipped."""
        store.emit(EventType.NODE_ADDED, logical_ts=0, node_id="a")
        with open(store._path, "a", encoding="utf-8") as f:
            # Missing "type" key triggers KeyError in from_dict
            f.write(json.dumps({"timestamp": 1.0}) + "\n")
        assert len(store.read_all()) == 1

    def test_emit_with_trace_id(self, store: FileEventStore):
        e = store.emit(EventType.TASK_CLAIMED, logical_ts=0, trace_id="t1", node_id="a")
        assert e.trace_id == "t1"
        events = store.read_all()
        assert events[0].trace_id == "t1"

    def test_emit_without_trace_id(self, store: FileEventStore):
        e = store.emit(EventType.NODE_ADDED, logical_ts=0, node_id="a")
        assert e.trace_id == ""

    def test_recover_last_hash_on_restart(self, tmp_path: Path):
        """A new FileEventStore instance recovers the last hash from disk."""
        s1 = FileEventStore(tmp_path)
        s1.emit(EventType.NODE_ADDED, logical_ts=0, node_id="a")
        e2 = s1.emit(EventType.NODE_ADDED, logical_ts=1, node_id="b")

        # Create a new store instance pointing at the same directory
        s2 = FileEventStore(tmp_path)
        e3 = s2.emit(EventType.NODE_ADDED, logical_ts=2, node_id="c")
        assert e3.prev_hash == e2.hash

    def test_recover_last_hash_empty_file(self, tmp_path: Path):
        """Recover returns empty string when file does not exist."""
        s = FileEventStore(tmp_path)
        assert s._last_hash == ""


# ===========================================================================
# Query methods
# ===========================================================================


class TestReadSince:
    """Tests for read_since (timestamp-based filtering)."""

    def test_read_since_returns_events_after_timestamp(self, populated_store: FileEventStore):
        all_events = populated_store.read_all()
        mid_ts = all_events[2].timestamp
        result = populated_store.read_since(mid_ts)
        # Should return events strictly AFTER mid_ts
        assert all(e.timestamp > mid_ts for e in result)
        assert len(result) >= 1

    def test_read_since_future_returns_empty(self, populated_store: FileEventStore):
        future = time.time() + 9999
        assert populated_store.read_since(future) == []

    def test_read_since_zero_returns_all(self, populated_store: FileEventStore):
        all_events = populated_store.read_all()
        result = populated_store.read_since(0.0)
        assert len(result) == len(all_events)

    def test_read_since_empty_store(self, store: FileEventStore):
        assert store.read_since(0.0) == []


class TestReadAt:
    """Tests for read_at (logical timestamp exact match)."""

    def test_read_at_existing_ts(self, populated_store: FileEventStore):
        e = populated_store.read_at(1)
        assert e is not None
        assert e.logical_ts == 1
        assert e.type == EventType.NODE_ADDED

    def test_read_at_nonexistent_ts(self, populated_store: FileEventStore):
        assert populated_store.read_at(999) is None

    def test_read_at_returns_first_match(self, store: FileEventStore):
        """When multiple events share a logical_ts, read_at returns the first."""
        store.emit(EventType.NODE_ADDED, logical_ts=10, node_id="x")
        store.emit(EventType.NODE_REMOVED, logical_ts=10, node_id="x")
        e = store.read_at(10)
        assert e is not None
        assert e.type == EventType.NODE_ADDED

    def test_read_at_empty_store(self, store: FileEventStore):
        assert store.read_at(0) is None


class TestReadRange:
    """Tests for read_range (inclusive logical_ts range)."""

    def test_read_range_full(self, populated_store: FileEventStore):
        result = populated_store.read_range(1, 6)
        assert len(result) == 6

    def test_read_range_subset(self, populated_store: FileEventStore):
        result = populated_store.read_range(2, 4)
        assert len(result) == 3
        assert all(2 <= e.logical_ts <= 4 for e in result)

    def test_read_range_single_ts(self, populated_store: FileEventStore):
        result = populated_store.read_range(3, 3)
        assert len(result) == 1
        assert result[0].logical_ts == 3

    def test_read_range_no_match(self, populated_store: FileEventStore):
        result = populated_store.read_range(100, 200)
        assert result == []

    def test_read_range_inverted_bounds_returns_empty(self, populated_store: FileEventStore):
        """from_ts > to_ts should return nothing (no event can satisfy)."""
        result = populated_store.read_range(5, 2)
        assert result == []

    def test_read_range_empty_store(self, store: FileEventStore):
        assert store.read_range(0, 100) == []


class TestReadUntil:
    """Tests for read_until (logical_ts upper bound, inclusive)."""

    def test_read_until_returns_events_up_to_ts(self, populated_store: FileEventStore):
        result = populated_store.read_until(3)
        assert len(result) == 3
        assert all(e.logical_ts <= 3 for e in result)

    def test_read_until_zero(self, populated_store: FileEventStore):
        result = populated_store.read_until(0)
        assert result == []

    def test_read_until_high_value(self, populated_store: FileEventStore):
        all_events = populated_store.read_all()
        result = populated_store.read_until(9999)
        assert len(result) == len(all_events)

    def test_read_until_empty_store(self, store: FileEventStore):
        assert store.read_until(100) == []


class TestReadByType:
    """Tests for read_by_type (filter by EventType)."""

    def test_read_by_type_node_added(self, populated_store: FileEventStore):
        result = populated_store.read_by_type(EventType.NODE_ADDED)
        assert len(result) == 2
        assert all(e.type == EventType.NODE_ADDED for e in result)

    def test_read_by_type_task_claimed(self, populated_store: FileEventStore):
        result = populated_store.read_by_type(EventType.TASK_CLAIMED)
        assert len(result) == 2

    def test_read_by_type_no_match(self, populated_store: FileEventStore):
        result = populated_store.read_by_type(EventType.NODE_REMOVED)
        assert result == []

    def test_read_by_type_single(self, populated_store: FileEventStore):
        result = populated_store.read_by_type(EventType.TASK_COMPLETED)
        assert len(result) == 1
        assert result[0].data["node_id"] == "a"

    def test_read_by_type_empty_store(self, store: FileEventStore):
        assert store.read_by_type(EventType.NODE_ADDED) == []


class TestReadByTrace:
    """Tests for read_by_trace (filter by trace_id)."""

    def test_read_by_trace_existing(self, populated_store: FileEventStore):
        result = populated_store.read_by_trace("trace-001")
        assert len(result) == 2
        assert all(e.trace_id == "trace-001" for e in result)

    def test_read_by_trace_single_event(self, populated_store: FileEventStore):
        result = populated_store.read_by_trace("trace-002")
        assert len(result) == 1

    def test_read_by_trace_nonexistent(self, populated_store: FileEventStore):
        result = populated_store.read_by_trace("nonexistent-trace")
        assert result == []

    def test_read_by_trace_empty_string(self, populated_store: FileEventStore):
        """Events without trace_id have trace_id='', so read_by_trace('') matches them."""
        result = populated_store.read_by_trace("")
        # The first 3 events in populated_store have no trace_id
        assert len(result) >= 3

    def test_read_by_trace_empty_store(self, store: FileEventStore):
        assert store.read_by_trace("anything") == []


class TestReadByNode:
    """Tests for read_by_node (matching node_id, source_node_id,
    corrective_node_id, and new_node_ids)."""

    def test_read_by_node_basic(self, populated_store: FileEventStore):
        result = populated_store.read_by_node("a")
        # NODE_ADDED(a), EDGE_ADDED(node_id=a), TASK_CLAIMED(a), TASK_COMPLETED(a)
        assert len(result) == 4

    def test_read_by_node_other(self, populated_store: FileEventStore):
        result = populated_store.read_by_node("b")
        # NODE_ADDED(b), TASK_CLAIMED(b)
        assert len(result) == 2

    def test_read_by_node_nonexistent(self, populated_store: FileEventStore):
        result = populated_store.read_by_node("nonexistent")
        assert result == []

    def test_read_by_node_matches_source_node_id(self, store: FileEventStore):
        store.emit(
            EventType.REWORK_REQUESTED,
            logical_ts=1,
            source_node_id="src",
            corrective_node_id="fix",
        )
        result = store.read_by_node("src")
        assert len(result) == 1

    def test_read_by_node_matches_corrective_node_id(self, store: FileEventStore):
        store.emit(
            EventType.REWORK_REQUESTED,
            logical_ts=1,
            source_node_id="src",
            corrective_node_id="fix",
        )
        result = store.read_by_node("fix")
        assert len(result) == 1

    def test_read_by_node_matches_new_node_ids(self, store: FileEventStore):
        store.emit(
            EventType.NODE_SPLIT,
            logical_ts=1,
            node_id="parent",
            new_node_ids=["child1", "child2"],
        )
        result = store.read_by_node("child1")
        assert len(result) == 1
        result2 = store.read_by_node("child2")
        assert len(result2) == 1

    def test_read_by_node_empty_store(self, store: FileEventStore):
        assert store.read_by_node("any") == []


# ===========================================================================
# verify_chain edge cases
# ===========================================================================


class TestVerifyChain:
    """Tests for the verify_chain hash-chain verification method."""

    def test_valid_chain(self, populated_store: FileEventStore):
        valid, msg = populated_store.verify_chain()
        assert valid is True
        assert msg == ""

    def test_empty_store_is_valid(self, store: FileEventStore):
        valid, msg = store.verify_chain()
        assert valid is True
        assert msg == ""

    def test_single_event_is_valid(self, store: FileEventStore):
        store.emit(EventType.NODE_ADDED, logical_ts=0, node_id="a")
        valid, msg = store.verify_chain()
        assert valid is True

    def test_tampered_hash_detected(self, store: FileEventStore):
        store.emit(EventType.NODE_ADDED, logical_ts=0, node_id="a")
        store.emit(EventType.NODE_ADDED, logical_ts=1, node_id="b")

        # Tamper with the hash of the first event on disk
        lines = store._path.read_text(encoding="utf-8").strip().split("\n")
        first = json.loads(lines[0])
        first["hash"] = "tampered_hash_value"
        lines[0] = json.dumps(first, ensure_ascii=False)
        store._path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        valid, msg = store.verify_chain()
        assert valid is False
        assert "hash mismatch" in msg or "prev_hash mismatch" in msg

    def test_tampered_content_detected(self, store: FileEventStore):
        """Changing event content while keeping the hash should be detected."""
        store.emit(EventType.NODE_ADDED, logical_ts=0, node_id="a")

        lines = store._path.read_text(encoding="utf-8").strip().split("\n")
        event_data = json.loads(lines[0])
        event_data["data"]["node_id"] = "INJECTED"
        # Keep the original hash — it should now be wrong
        lines[0] = json.dumps(event_data, ensure_ascii=False)
        store._path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        valid, msg = store.verify_chain()
        assert valid is False
        assert "tampered" in msg

    def test_prev_hash_mismatch_detected(self, store: FileEventStore):
        """Swapping event order should break prev_hash linkage."""
        store.emit(EventType.NODE_ADDED, logical_ts=0, node_id="a")
        store.emit(EventType.NODE_ADDED, logical_ts=1, node_id="b")
        store.emit(EventType.NODE_ADDED, logical_ts=2, node_id="c")

        # Swap events 1 and 2 (0-indexed)
        lines = store._path.read_text(encoding="utf-8").strip().split("\n")
        lines[1], lines[2] = lines[2], lines[1]
        store._path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        valid, msg = store.verify_chain()
        assert valid is False
        assert "prev_hash mismatch" in msg

    def test_events_without_hash_are_skipped(self, store: FileEventStore):
        """Events lacking a hash field are silently skipped during verification."""
        # Write an event without hash/prev_hash fields
        raw_event = {
            "id": "legacy1",
            "type": "node_added",
            "timestamp": 1.0,
            "logical_ts": 0,
            "data": {"node_id": "x"},
        }
        store._path.parent.mkdir(parents=True, exist_ok=True)
        with open(store._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(raw_event) + "\n")

        valid, msg = store.verify_chain()
        assert valid is True
        assert msg == ""

    def test_chain_valid_after_clear_and_rewrite(self, store: FileEventStore):
        """After clear() + new events, the chain is valid from scratch."""
        store.emit(EventType.NODE_ADDED, logical_ts=0, node_id="a")
        store.clear()
        store.emit(EventType.NODE_ADDED, logical_ts=0, node_id="b")
        store.emit(EventType.NODE_ADDED, logical_ts=1, node_id="c")

        valid, msg = store.verify_chain()
        assert valid is True

    def test_deleted_middle_event_detected(self, store: FileEventStore):
        """Removing an event from the middle breaks the chain."""
        store.emit(EventType.NODE_ADDED, logical_ts=0, node_id="a")
        store.emit(EventType.NODE_ADDED, logical_ts=1, node_id="b")
        store.emit(EventType.NODE_ADDED, logical_ts=2, node_id="c")

        # Remove the second event
        lines = store._path.read_text(encoding="utf-8").strip().split("\n")
        del lines[1]
        store._path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        valid, msg = store.verify_chain()
        assert valid is False
        assert "prev_hash mismatch" in msg


# ===========================================================================
# summary
# ===========================================================================


class TestSummary:
    def test_summary_counts(self, populated_store: FileEventStore):
        s = populated_store.summary()
        assert s["node_added"] == 2
        assert s["edge_added"] == 1
        assert s["task_claimed"] == 2
        assert s["task_completed"] == 1

    def test_summary_empty(self, store: FileEventStore):
        assert store.summary() == {}
