"""Unit tests for cascade.replay — event replay to rebuild graph state.

Tests each per-event-type handler and the verify() function.
"""

import time
from unittest.mock import MagicMock

import pytest

from cascade.core.cascade import Cascade
from cascade.core.node import Node
from cascade.core.state import NodeState
from cascade.events import Event, EventType
from cascade.replay import replay, verify


def _evt(event_type: EventType, data: dict | None = None) -> Event:
    return Event(type=event_type, timestamp=time.time(), data=data or {})


# ---------------------------------------------------------------------------
# replay() top-level
# ---------------------------------------------------------------------------


class TestReplay:
    def test_empty_events(self):
        c = replay([])
        assert len(c.nodes) == 0

    def test_single_node_added(self):
        c = replay([_evt(EventType.NODE_ADDED, {"node_id": "a"})])
        assert "a" in c.nodes
        assert c.nodes["a"].state == NodeState.READY

    def test_events_applied_in_order(self):
        events = [
            _evt(EventType.NODE_ADDED, {"node_id": "a"}),
            _evt(EventType.TASK_CLAIMED, {"node_id": "a", "agent_id": "w1"}),
            _evt(EventType.TASK_COMPLETED, {"node_id": "a"}),
        ]
        c = replay(events)
        assert c.nodes["a"].state == NodeState.COMPLETED

    def test_noop_events_ignored(self):
        events = [
            _evt(EventType.NODE_ADDED, {"node_id": "a"}),
            _evt(EventType.EDGE_ADDED, {"from": "a", "to": "b"}),
            _evt(EventType.EDGE_REMOVED, {"from": "a", "to": "b"}),
        ]
        c = replay(events)
        assert len(c.nodes) == 1


# ---------------------------------------------------------------------------
# verify()
# ---------------------------------------------------------------------------


class TestVerify:
    def test_identical_returns_empty(self):
        events = [_evt(EventType.NODE_ADDED, {"node_id": "a"})]
        snapshot = Cascade()
        snapshot.add_node(Node(id="a"))
        diffs = verify(events, snapshot)
        assert diffs == []

    def test_extra_node_in_replay(self):
        events = [
            _evt(EventType.NODE_ADDED, {"node_id": "a"}),
            _evt(EventType.NODE_ADDED, {"node_id": "b"}),
        ]
        snapshot = Cascade()
        snapshot.add_node(Node(id="a"))
        diffs = verify(events, snapshot)
        assert any("b" in d and "replay" in d for d in diffs)

    def test_extra_node_in_snapshot(self):
        events = [_evt(EventType.NODE_ADDED, {"node_id": "a"})]
        snapshot = Cascade()
        snapshot.add_node(Node(id="a"))
        snapshot.add_node(Node(id="b"))
        diffs = verify(events, snapshot)
        assert any("b" in d and "snapshot" in d for d in diffs)

    def test_state_mismatch(self):
        events = [
            _evt(EventType.NODE_ADDED, {"node_id": "a"}),
            _evt(EventType.TASK_CLAIMED, {"node_id": "a", "agent_id": "w1"}),
        ]
        snapshot = Cascade()
        snapshot.add_node(Node(id="a", state=NodeState.READY))
        diffs = verify(events, snapshot)
        assert any("state" in d for d in diffs)

    def test_agent_mismatch(self):
        events = [
            _evt(EventType.NODE_ADDED, {"node_id": "a"}),
            _evt(EventType.TASK_CLAIMED, {"node_id": "a", "agent_id": "w1"}),
        ]
        snapshot = Cascade()
        snapshot.add_node(Node(id="a", state=NodeState.ACTIVE, agent_id="w2"))
        diffs = verify(events, snapshot)
        assert any("agent" in d for d in diffs)

    def test_edge_mismatch(self):
        events = [
            _evt(EventType.NODE_ADDED, {"node_id": "a"}),
            _evt(
                EventType.NODE_ADDED,
                {
                    "node_id": "b",
                    "deps_contracts": [{"node_id": "a", "expectation": "E", "promise": "P"}],
                },
            ),
        ]
        snapshot = Cascade()
        snapshot.add_node(Node(id="a"))
        snapshot.add_node(Node(id="b"))
        diffs = verify(events, snapshot)
        assert any("edge" in d for d in diffs)


# ---------------------------------------------------------------------------
# _handle_node_added
# ---------------------------------------------------------------------------


class TestHandleNodeAdded:
    def test_duplicate_node_skipped(self):
        events = [
            _evt(EventType.NODE_ADDED, {"node_id": "a"}),
            _evt(EventType.NODE_ADDED, {"node_id": "a"}),
        ]
        c = replay(events)
        assert "a" in c.nodes

    def test_deps_contracts_add_edges(self):
        events = [
            _evt(EventType.NODE_ADDED, {"node_id": "a"}),
            _evt(
                EventType.NODE_ADDED,
                {
                    "node_id": "b",
                    "deps_contracts": [{"node_id": "a", "expectation": "E", "promise": "P"}],
                },
            ),
        ]
        c = replay(events)
        assert ("a", "b") in c.contracts

    def test_dependent_contracts_add_edges(self):
        events = [
            _evt(EventType.NODE_ADDED, {"node_id": "b"}),
            _evt(
                EventType.NODE_ADDED,
                {
                    "node_id": "a",
                    "dependent_contracts": [{"node_id": "b", "expectation": "E", "promise": "P"}],
                },
            ),
        ]
        c = replay(events)
        assert ("a", "b") in c.contracts

    def test_deps_contract_skipped_if_dep_missing(self):
        events = [
            _evt(
                EventType.NODE_ADDED,
                {
                    "node_id": "b",
                    "deps_contracts": [{"node_id": "a", "expectation": "E", "promise": "P"}],
                },
            ),
        ]
        c = replay(events)
        assert "b" in c.nodes
        assert ("a", "b") not in c.contracts


# ---------------------------------------------------------------------------
# _handle_node_removed
# ---------------------------------------------------------------------------


class TestHandleNodeRemoved:
    def test_removes_non_active_nodes(self):
        events = [
            _evt(EventType.NODE_ADDED, {"node_id": "a"}),
            _evt(EventType.NODE_REMOVED, {"affected_nodes": ["a"]}),
        ]
        c = replay(events)
        assert "a" not in c.nodes

    def test_active_node_not_removed(self):
        events = [
            _evt(EventType.NODE_ADDED, {"node_id": "a"}),
            _evt(EventType.TASK_CLAIMED, {"node_id": "a", "agent_id": "w1"}),
            _evt(EventType.NODE_REMOVED, {"affected_nodes": ["a"]}),
        ]
        c = replay(events)
        assert "a" in c.nodes

    def test_nonexistent_node_ignored(self):
        events = [
            _evt(EventType.NODE_REMOVED, {"affected_nodes": ["ghost"]}),
        ]
        c = replay(events)
        assert len(c.nodes) == 0


# ---------------------------------------------------------------------------
# _handle_node_split
# ---------------------------------------------------------------------------


class TestHandleNodeSplit:
    def test_adds_new_nodes_and_removes_parent(self):
        events = [
            _evt(EventType.NODE_ADDED, {"node_id": "parent"}),
            _evt(
                EventType.NODE_SPLIT,
                {
                    "node_id": "parent",
                    "new_node_ids": ["c1", "c2"],
                },
            ),
        ]
        c = replay(events)
        assert "c1" in c.nodes
        assert "c2" in c.nodes
        assert "parent" not in c.nodes

    def test_active_parent_not_removed(self):
        events = [
            _evt(EventType.NODE_ADDED, {"node_id": "parent"}),
            _evt(EventType.TASK_CLAIMED, {"node_id": "parent", "agent_id": "w1"}),
            _evt(
                EventType.NODE_SPLIT,
                {
                    "node_id": "parent",
                    "new_node_ids": ["c1"],
                },
            ),
        ]
        c = replay(events)
        assert "parent" in c.nodes
        assert "c1" in c.nodes

    def test_duplicate_new_node_skipped(self):
        events = [
            _evt(EventType.NODE_ADDED, {"node_id": "c1"}),
            _evt(EventType.NODE_ADDED, {"node_id": "parent"}),
            _evt(
                EventType.NODE_SPLIT,
                {
                    "node_id": "parent",
                    "new_node_ids": ["c1", "c2"],
                },
            ),
        ]
        c = replay(events)
        assert "c1" in c.nodes
        assert "c2" in c.nodes


# ---------------------------------------------------------------------------
# _handle_node_refined
# ---------------------------------------------------------------------------


class TestHandleNodeRefined:
    def test_adds_edge(self):
        events = [
            _evt(EventType.NODE_ADDED, {"node_id": "a"}),
            _evt(EventType.NODE_ADDED, {"node_id": "b"}),
            _evt(
                EventType.NODE_REFINED,
                {
                    "node_id": "b",
                    "dependency_id": "a",
                    "expectation": "E",
                    "promise": "P",
                },
            ),
        ]
        c = replay(events)
        assert ("a", "b") in c.contracts

    def test_missing_nodes_ignored(self):
        events = [
            _evt(
                EventType.NODE_REFINED,
                {
                    "node_id": "b",
                    "dependency_id": "a",
                    "expectation": "E",
                    "promise": "P",
                },
            ),
        ]
        c = replay(events)
        assert len(c.nodes) == 0


# ---------------------------------------------------------------------------
# _handle_node_edited
# ---------------------------------------------------------------------------


class TestHandleNodeEdited:
    def test_state_transition(self):
        events = [
            _evt(EventType.NODE_ADDED, {"node_id": "a"}),
            _evt(
                EventType.NODE_ADDED,
                {
                    "node_id": "b",
                    "deps_contracts": [{"node_id": "a", "expectation": "E", "promise": "P"}],
                },
            ),
            _evt(EventType.TASK_CLAIMED, {"node_id": "a", "agent_id": "w1"}),
            _evt(EventType.NODE_EDITED, {"node_id": "a", "new_state": "COMPLETED"}),
        ]
        c = replay(events)
        assert c.nodes["a"].state == NodeState.COMPLETED

    def test_completed_via_edit_unblocks_dependents(self):
        events = [
            _evt(EventType.NODE_ADDED, {"node_id": "a"}),
            _evt(
                EventType.NODE_ADDED,
                {
                    "node_id": "b",
                    "deps_contracts": [{"node_id": "a", "expectation": "E", "promise": "P"}],
                },
            ),
            _evt(EventType.TASK_CLAIMED, {"node_id": "a", "agent_id": "w1"}),
            _evt(EventType.NODE_EDITED, {"node_id": "a", "new_state": "COMPLETED"}),
        ]
        c = replay(events)
        assert c.nodes["b"].state == NodeState.READY

    def test_nonexistent_node_ignored(self):
        events = [
            _evt(EventType.NODE_EDITED, {"node_id": "ghost", "new_state": "READY"}),
        ]
        c = replay(events)
        assert len(c.nodes) == 0

    def test_context_summary_updated(self):
        events = [
            _evt(EventType.NODE_ADDED, {"node_id": "a"}),
            _evt(
                EventType.NODE_EDITED,
                {
                    "node_id": "a",
                    "context": {"summary": "new summary"},
                },
            ),
        ]
        c = replay(events)
        assert c.nodes["a"].context is not None
        assert c.nodes["a"].context.summary == "new summary"

    def test_context_critical_merged(self):
        events = [
            _evt(EventType.NODE_ADDED, {"node_id": "a"}),
            _evt(
                EventType.NODE_EDITED,
                {
                    "node_id": "a",
                    "context": {"critical": {"k1": "v1"}},
                },
            ),
            _evt(
                EventType.NODE_EDITED,
                {
                    "node_id": "a",
                    "context": {"critical": {"k2": "v2"}},
                },
            ),
        ]
        c = replay(events)
        assert c.nodes["a"].context.critical == {"k1": "v1", "k2": "v2"}

    def test_context_artifacts_with_content_store(self):
        store = MagicMock()
        store.get.return_value = "resolved content"
        events = [
            _evt(EventType.NODE_ADDED, {"node_id": "a"}),
            _evt(
                EventType.NODE_EDITED,
                {
                    "node_id": "a",
                    "context": {"artifacts_ref": "abc123"},
                },
            ),
        ]
        c = replay(events, content=store)
        assert c.nodes["a"].context.artifacts == "resolved content"
        store.get.assert_called_once_with("abc123")

    def test_context_artifacts_without_content_store(self):
        events = [
            _evt(EventType.NODE_ADDED, {"node_id": "a"}),
            _evt(
                EventType.NODE_EDITED,
                {
                    "node_id": "a",
                    "context": {"artifacts_ref": "abc123"},
                },
            ),
        ]
        c = replay(events, content=None)
        assert c.nodes["a"].context.artifacts == ""

    def test_no_state_change_when_no_new_state(self):
        events = [
            _evt(EventType.NODE_ADDED, {"node_id": "a"}),
            _evt(
                EventType.NODE_EDITED,
                {
                    "node_id": "a",
                    "context": {"summary": "update"},
                },
            ),
        ]
        c = replay(events)
        assert c.nodes["a"].state == NodeState.READY


# ---------------------------------------------------------------------------
# _handle_task_claimed
# ---------------------------------------------------------------------------


class TestHandleTaskClaimed:
    def test_claim_transitions_to_active(self):
        events = [
            _evt(EventType.NODE_ADDED, {"node_id": "a"}),
            _evt(EventType.TASK_CLAIMED, {"node_id": "a", "agent_id": "w1"}),
        ]
        c = replay(events)
        assert c.nodes["a"].state == NodeState.ACTIVE
        assert c.nodes["a"].agent_id == "w1"

    def test_claim_sets_timeout(self):
        events = [
            _evt(EventType.NODE_ADDED, {"node_id": "a"}),
            _evt(
                EventType.TASK_CLAIMED,
                {
                    "node_id": "a",
                    "agent_id": "w1",
                    "timeout": 60,
                },
            ),
        ]
        c = replay(events)
        assert c.nodes["a"].timeout == 60.0

    def test_claim_sets_claimed_at(self):
        ts = time.time()
        events = [
            _evt(EventType.NODE_ADDED, {"node_id": "a"}),
            _evt(
                EventType.TASK_CLAIMED,
                {
                    "node_id": "a",
                    "agent_id": "w1",
                    "claimed_at": ts,
                },
            ),
        ]
        c = replay(events)
        assert c.nodes["a"].claimed_at == ts

    def test_claim_nonexistent_ignored(self):
        events = [
            _evt(EventType.TASK_CLAIMED, {"node_id": "ghost", "agent_id": "w1"}),
        ]
        c = replay(events)
        assert len(c.nodes) == 0

    def test_claim_increments_epoch(self):
        events = [
            _evt(EventType.NODE_ADDED, {"node_id": "a"}),
            _evt(EventType.TASK_CLAIMED, {"node_id": "a", "agent_id": "w1"}),
        ]
        c = replay(events)
        assert c.epoch > 0


# ---------------------------------------------------------------------------
# _handle_task_completed
# ---------------------------------------------------------------------------


class TestHandleTaskCompleted:
    def test_complete_transitions_and_clears_agent(self):
        events = [
            _evt(EventType.NODE_ADDED, {"node_id": "a"}),
            _evt(EventType.TASK_CLAIMED, {"node_id": "a", "agent_id": "w1", "timeout": 30}),
            _evt(EventType.TASK_COMPLETED, {"node_id": "a"}),
        ]
        c = replay(events)
        assert c.nodes["a"].state == NodeState.COMPLETED
        assert c.nodes["a"].agent_id is None
        assert c.nodes["a"].claimed_at is None
        assert c.nodes["a"].timeout is None

    def test_complete_unblocks_dependents(self):
        events = [
            _evt(EventType.NODE_ADDED, {"node_id": "a"}),
            _evt(
                EventType.NODE_ADDED,
                {
                    "node_id": "b",
                    "deps_contracts": [{"node_id": "a", "expectation": "E", "promise": "P"}],
                },
            ),
            _evt(EventType.TASK_CLAIMED, {"node_id": "a", "agent_id": "w1"}),
            _evt(EventType.TASK_COMPLETED, {"node_id": "a"}),
        ]
        c = replay(events)
        assert c.nodes["b"].state == NodeState.READY

    def test_complete_with_context(self):
        store = MagicMock()
        store.get.return_value = "artifact content"
        events = [
            _evt(EventType.NODE_ADDED, {"node_id": "a"}),
            _evt(EventType.TASK_CLAIMED, {"node_id": "a", "agent_id": "w1"}),
            _evt(
                EventType.TASK_COMPLETED,
                {
                    "node_id": "a",
                    "context": {
                        "summary": "done",
                        "critical": {"output": "result"},
                        "artifacts_ref": "ref1",
                    },
                },
            ),
        ]
        c = replay(events, content=store)
        assert c.nodes["a"].context.summary == "done"
        assert c.nodes["a"].context.critical["output"] == "result"
        assert c.nodes["a"].context.artifacts == "artifact content"

    def test_complete_nonexistent_ignored(self):
        events = [
            _evt(EventType.TASK_COMPLETED, {"node_id": "ghost"}),
        ]
        c = replay(events)
        assert len(c.nodes) == 0


# ---------------------------------------------------------------------------
# _handle_task_failed
# ---------------------------------------------------------------------------


class TestHandleTaskFailed:
    def test_fail_single_node(self):
        events = [
            _evt(EventType.NODE_ADDED, {"node_id": "a"}),
            _evt(EventType.TASK_CLAIMED, {"node_id": "a", "agent_id": "w1", "timeout": 30}),
            _evt(EventType.TASK_FAILED, {"node_id": "a"}),
        ]
        c = replay(events)
        assert c.nodes["a"].state == NodeState.FAILED
        assert c.nodes["a"].agent_id is None
        assert c.nodes["a"].claimed_at is None
        assert c.nodes["a"].timeout is None

    def test_fail_cascades_to_affected(self):
        events = [
            _evt(EventType.NODE_ADDED, {"node_id": "a"}),
            _evt(EventType.NODE_ADDED, {"node_id": "b"}),
            _evt(EventType.TASK_FAILED, {"affected": ["a", "b"]}),
        ]
        c = replay(events)
        assert c.nodes["a"].state == NodeState.FAILED
        assert c.nodes["b"].state == NodeState.FAILED

    def test_fail_skips_terminal_nodes(self):
        events = [
            _evt(EventType.NODE_ADDED, {"node_id": "a"}),
            _evt(EventType.TASK_CLAIMED, {"node_id": "a", "agent_id": "w1"}),
            _evt(EventType.TASK_COMPLETED, {"node_id": "a"}),
            _evt(EventType.TASK_FAILED, {"affected": ["a"]}),
        ]
        c = replay(events)
        assert c.nodes["a"].state == NodeState.COMPLETED

    def test_fail_nonexistent_ignored(self):
        events = [
            _evt(EventType.TASK_FAILED, {"node_id": "ghost"}),
        ]
        c = replay(events)
        assert len(c.nodes) == 0


# ---------------------------------------------------------------------------
# _handle_task_released
# ---------------------------------------------------------------------------


class TestHandleTaskReleased:
    def test_release_returns_to_ready(self):
        events = [
            _evt(EventType.NODE_ADDED, {"node_id": "a"}),
            _evt(
                EventType.TASK_CLAIMED,
                {
                    "node_id": "a",
                    "agent_id": "w1",
                    "claimed_at": time.time(),
                    "timeout": 30,
                },
            ),
            _evt(EventType.TASK_RELEASED, {"node_id": "a"}),
        ]
        c = replay(events)
        assert c.nodes["a"].state == NodeState.READY
        assert c.nodes["a"].agent_id is None
        assert c.nodes["a"].claimed_at is None
        assert c.nodes["a"].timeout is None

    def test_release_nonexistent_ignored(self):
        events = [
            _evt(EventType.TASK_RELEASED, {"node_id": "ghost"}),
        ]
        c = replay(events)
        assert len(c.nodes) == 0


# ---------------------------------------------------------------------------
# _handle_task_timed_out
# ---------------------------------------------------------------------------


class TestHandleTaskTimedOut:
    def test_timeout_same_as_release(self):
        events = [
            _evt(EventType.NODE_ADDED, {"node_id": "a"}),
            _evt(
                EventType.TASK_CLAIMED,
                {
                    "node_id": "a",
                    "agent_id": "w1",
                    "timeout": 10,
                },
            ),
            _evt(EventType.TASK_TIMED_OUT, {"node_id": "a"}),
        ]
        c = replay(events)
        assert c.nodes["a"].state == NodeState.READY
        assert c.nodes["a"].agent_id is None
        assert c.nodes["a"].timeout is None


# ---------------------------------------------------------------------------
# _handle_rework
# ---------------------------------------------------------------------------


class TestHandleRework:
    def test_creates_corrective_node(self):
        events = [
            _evt(EventType.NODE_ADDED, {"node_id": "source"}),
            _evt(
                EventType.REWORK_REQUESTED,
                {
                    "source_node_id": "source",
                    "corrective_node_id": "fix",
                    "requesting_node_id": "req",
                },
            ),
        ]
        c = replay(events)
        assert "fix" in c.nodes

    def test_adds_source_to_corrective_edge(self):
        events = [
            _evt(EventType.NODE_ADDED, {"node_id": "source"}),
            _evt(
                EventType.REWORK_REQUESTED,
                {
                    "source_node_id": "source",
                    "corrective_node_id": "fix",
                    "source_contract": {"expectation": "E", "promise": "P"},
                },
            ),
        ]
        c = replay(events)
        assert ("source", "fix") in c.contracts

    def test_adds_corrective_to_requesting_edge(self):
        events = [
            _evt(EventType.NODE_ADDED, {"node_id": "req"}),
            _evt(
                EventType.REWORK_REQUESTED,
                {
                    "source_node_id": "source",
                    "corrective_node_id": "fix",
                    "requesting_node_id": "req",
                    "corrective_contract": {"expectation": "E", "promise": "P"},
                },
            ),
        ]
        c = replay(events)
        assert ("fix", "req") in c.contracts

    def test_requesting_active_node_crashes(self):
        """BUG: ACTIVE -> PENDING is not a valid transition.

        _handle_rework tries node.update_state(NodeState.PENDING) on an
        ACTIVE node, but the state machine forbids this. This crashes replay
        instead of gracefully handling the rework. Filed as upstream issue.
        """
        from cascade.errors import InvalidTransitionError

        events = [
            _evt(EventType.NODE_ADDED, {"node_id": "req"}),
            _evt(
                EventType.TASK_CLAIMED,
                {
                    "node_id": "req",
                    "agent_id": "w1",
                    "claimed_at": time.time(),
                    "timeout": 30,
                },
            ),
            _evt(
                EventType.REWORK_REQUESTED,
                {
                    "source_node_id": "source",
                    "corrective_node_id": "fix",
                    "requesting_node_id": "req",
                    "corrective_contract": {"expectation": "E", "promise": "P"},
                },
            ),
        ]
        with pytest.raises(InvalidTransitionError, match="ACTIVE -> PENDING"):
            replay(events)

    def test_requesting_ready_node_becomes_pending_via_edge(self):
        """When a READY node gets a new dependency (corrective -> req),
        readiness recomputation moves it to PENDING."""
        events = [
            _evt(EventType.NODE_ADDED, {"node_id": "req"}),
            _evt(
                EventType.REWORK_REQUESTED,
                {
                    "source_node_id": "source",
                    "corrective_node_id": "fix",
                    "requesting_node_id": "req",
                    "corrective_contract": {"expectation": "E", "promise": "P"},
                },
            ),
        ]
        c = replay(events)
        assert c.nodes["req"].state == NodeState.PENDING


# ---------------------------------------------------------------------------
# _handle_node_cancelled
# ---------------------------------------------------------------------------


class TestHandleNodeCancelled:
    def test_cancels_non_terminal(self):
        events = [
            _evt(EventType.NODE_ADDED, {"node_id": "a"}),
            _evt(EventType.NODE_CANCELLED, {"node_id": "a"}),
        ]
        c = replay(events)
        assert c.nodes["a"].state == NodeState.CANCELLED

    def test_completed_not_cancelled_despite_valid_transition(self):
        """BUG: is_terminal() blocks COMPLETED -> CANCELLED, but the state
        machine (state.py line 88) allows it. The handler's guard is too broad.
        Filed as upstream issue."""
        events = [
            _evt(EventType.NODE_ADDED, {"node_id": "a"}),
            _evt(EventType.TASK_CLAIMED, {"node_id": "a", "agent_id": "w1"}),
            _evt(EventType.TASK_COMPLETED, {"node_id": "a"}),
            _evt(EventType.NODE_CANCELLED, {"node_id": "a"}),
        ]
        c = replay(events)
        # Should be CANCELLED per state machine, but handler skips it
        assert c.nodes["a"].state == NodeState.COMPLETED

    def test_nonexistent_ignored(self):
        events = [
            _evt(EventType.NODE_CANCELLED, {"node_id": "ghost"}),
        ]
        c = replay(events)
        assert len(c.nodes) == 0
