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

"""Tests for event sourcing — event store and tool integration."""


from cascade.events import EventType
from tools import add_node, finish_task, get_task
from tools.history import history


class TestEventStore:
    """Tests for the EventStore."""

    def test_emit_and_read(self, temp_storage):
        store = temp_storage.events
        store.emit(EventType.NODE_ADDED, node_id="test")

        events = store.read_all()
        assert len(events) == 1
        assert events[0].type == EventType.NODE_ADDED
        assert events[0].data["node_id"] == "test"

    def test_read_empty(self, temp_storage):
        assert temp_storage.events.read_all() == []

    def test_read_by_type(self, temp_storage):
        store = temp_storage.events
        store.emit(EventType.NODE_ADDED, node_id="a")
        store.emit(EventType.TASK_CLAIMED, node_id="a", agent_id="x")
        store.emit(EventType.NODE_ADDED, node_id="b")

        claimed = store.read_by_type(EventType.TASK_CLAIMED)
        assert len(claimed) == 1
        assert claimed[0].data["agent_id"] == "x"

    def test_read_by_node(self, temp_storage):
        store = temp_storage.events
        store.emit(EventType.NODE_ADDED, node_id="a")
        store.emit(EventType.NODE_ADDED, node_id="b")
        store.emit(EventType.TASK_CLAIMED, node_id="a", agent_id="x")

        a_events = store.read_by_node("a")
        assert len(a_events) == 2  # added + claimed

    def test_count_and_summary(self, temp_storage):
        store = temp_storage.events
        store.emit(EventType.NODE_ADDED, node_id="a")
        store.emit(EventType.NODE_ADDED, node_id="b")
        store.emit(EventType.TASK_CLAIMED, node_id="a", agent_id="x")

        assert store.count == 3
        summary = store.summary()
        assert summary["node_added"] == 2
        assert summary["task_claimed"] == 1

    def test_event_serialization(self, temp_storage):
        store = temp_storage.events
        store.emit(EventType.REWORK_REQUESTED, source_node_id="a",
                   corrective_node_id="a_fix", reason="wrong")

        events = store.read_all()
        assert events[0].data["reason"] == "wrong"


class TestEventIntegration:
    """Tests that tools emit events automatically."""

    def test_add_node_emits_event(self, temp_storage):
        add_node.add_node(temp_storage, {"node_id": "task_a"})

        events = temp_storage.events.read_all()
        assert len(events) == 1
        assert events[0].type == EventType.NODE_ADDED
        assert events[0].data["node_id"] == "task_a"

    def test_claim_emits_event(self, temp_storage):
        add_node.add_node(temp_storage, {"node_id": "task_a"})
        get_task.get_task(temp_storage, {"agent_id": "agent-1", "task_id": "task_a"})

        events = temp_storage.events.read_by_type(EventType.TASK_CLAIMED)
        assert len(events) == 1
        assert events[0].data["agent_id"] == "agent-1"

    def test_complete_emits_event(self, temp_storage):
        add_node.add_node(temp_storage, {"node_id": "task_a"})
        get_task.get_task(temp_storage, {"agent_id": "agent-1", "task_id": "task_a"})
        finish_task.finish_task(temp_storage, {"task_id": "task_a", "success": True})

        events = temp_storage.events.read_by_type(EventType.TASK_COMPLETED)
        assert len(events) == 1

    def test_fail_emits_event(self, temp_storage):
        add_node.add_node(temp_storage, {"node_id": "task_a"})
        get_task.get_task(temp_storage, {"agent_id": "agent-1", "task_id": "task_a"})
        finish_task.finish_task(temp_storage, {"task_id": "task_a", "success": False, "result": "broke"})

        events = temp_storage.events.read_by_type(EventType.TASK_FAILED)
        assert len(events) == 1
        assert events[0].data["reason"] == "broke"

    def test_release_emits_event(self, temp_storage):
        add_node.add_node(temp_storage, {"node_id": "task_a"})
        get_task.get_task(temp_storage, {"agent_id": "agent-1", "task_id": "task_a"})
        finish_task.finish_task(temp_storage, {"task_id": "task_a", "release": True, "result": "stuck"})

        events = temp_storage.events.read_by_type(EventType.TASK_RELEASED)
        assert len(events) == 1

    def test_full_lifecycle_event_trail(self, temp_storage):
        """End-to-end: add -> claim -> complete -> claim next."""
        add_node.add_node(temp_storage, {"node_id": "a"})
        add_node.add_node(temp_storage, {
            "node_id": "b",
            "dependencies": ["a"],
            "expectations": [{"node_id": "a", "expectation": "E", "promise": "P"}],
        })
        get_task.get_task(temp_storage, {"agent_id": "agent-1"})
        finish_task.finish_task(temp_storage, {"task_id": "a", "success": True})
        get_task.get_task(temp_storage, {"agent_id": "agent-2", "task_id": "b"})

        all_events = temp_storage.events.read_all()
        types = [e.type for e in all_events]
        assert types == [
            EventType.NODE_ADDED,      # a
            EventType.NODE_ADDED,      # b
            EventType.TASK_CLAIMED,    # agent-1 claims a
            EventType.TASK_COMPLETED,  # a completed
            EventType.TASK_CLAIMED,    # agent-2 claims b
        ]


class TestHistoryTool:
    """Tests for the history query tool."""

    def test_history_all(self, temp_storage):
        add_node.add_node(temp_storage, {"node_id": "a"})
        add_node.add_node(temp_storage, {"node_id": "b"})

        result = history(temp_storage, {})
        assert result["success"]
        assert result["data"]["count"] == 2

    def test_history_by_node(self, temp_storage):
        add_node.add_node(temp_storage, {"node_id": "a"})
        add_node.add_node(temp_storage, {"node_id": "b"})

        result = history(temp_storage, {"node_id": "a"})
        assert result["success"]
        assert result["data"]["count"] == 1

    def test_history_summary(self, temp_storage):
        add_node.add_node(temp_storage, {"node_id": "a"})
        get_task.get_task(temp_storage, {"agent_id": "x"})

        result = history(temp_storage, {"summary": True})
        assert result["success"]
        assert result["data"]["summary"]["node_added"] == 1
        assert result["data"]["summary"]["task_claimed"] == 1

    def test_history_last_n(self, temp_storage):
        add_node.add_node(temp_storage, {"node_id": "a"})
        add_node.add_node(temp_storage, {"node_id": "b"})
        add_node.add_node(temp_storage, {"node_id": "c"})

        result = history(temp_storage, {"last_n": 2})
        assert result["data"]["count"] == 2
