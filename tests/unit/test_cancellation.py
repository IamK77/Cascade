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

"""Tests for CancellationToken and CancellationPropagator.

Focuses on: cascade cancellation through DAG, terminal state guards,
callback lifecycle, and cross-component invariants.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from cascade.context.cancellation import CancellationPropagator, CancellationToken
from cascade.core.cascade import Cascade
from cascade.core.node import Node
from cascade.core.state import NodeState
from cascade.errors import CancelledError
from cascade.types import TokenStatus

# ---------------------------------------------------------------------------
# CancellationToken
# ---------------------------------------------------------------------------


class TestCancellationToken:
    def test_initial_state(self):
        token = CancellationToken()
        assert not token.is_cancelled
        assert token.reason is None
        assert bool(token) is True

    def test_cancel(self):
        token = CancellationToken()
        token.cancel("test reason")
        assert token.is_cancelled
        assert token.reason == "test reason"
        assert bool(token) is False

    def test_cancel_idempotent(self):
        """Cancelling twice should not overwrite the reason."""
        token = CancellationToken()
        token.cancel("first")
        token.cancel("second")
        assert token.reason == "first"

    def test_cancel_no_reason(self):
        token = CancellationToken()
        token.cancel()
        assert token.is_cancelled
        assert token.reason is None

    def test_throw_if_cancelled(self):
        token = CancellationToken()
        token.throw_if_cancelled()

        token.cancel("abort")
        with pytest.raises(CancelledError, match="abort"):
            token.throw_if_cancelled()

    def test_callback_fires_on_cancel(self):
        token = CancellationToken()
        called = []
        token.register_callback(lambda: called.append(1))
        token.register_callback(lambda: called.append(2))
        token.cancel()
        assert called == [1, 2]

    def test_callback_on_already_cancelled_fires_immediately(self):
        token = CancellationToken()
        token.cancel()
        called = []
        token.register_callback(lambda: called.append("immediate"))
        assert called == ["immediate"]

    def test_unregister_callback(self):
        token = CancellationToken()
        called = []
        unregister = token.register_callback(lambda: called.append(1))
        unregister()
        token.cancel()
        assert called == []

    def test_unregister_on_already_cancelled_is_noop(self):
        """Registering on a cancelled token returns a no-op unregister."""
        token = CancellationToken()
        token.cancel()
        unregister = token.register_callback(lambda: None)
        unregister()

    def test_get_event_sets_on_cancel(self):
        token = CancellationToken()
        event = token.get_event()
        assert not event.is_set()
        token.cancel()
        assert event.is_set()

    def test_get_event_already_cancelled(self):
        """Getting event after cancel should return an already-set event."""
        token = CancellationToken()
        token.cancel()
        event = token.get_event()
        assert event.is_set()

    def test_notify_bridges_token_status(self):
        """notify() implements CancelNotifier protocol."""
        token = CancellationToken()
        status = TokenStatus(
            node_id="a",
            agent_id="w1",
            valid=False,
            reason="released",
            claimed_at=0.0,
            invalidated_at=1.0,
        )
        token.notify(status)
        assert token.is_cancelled
        assert token.reason == "released"


# ---------------------------------------------------------------------------
# CancellationPropagator
# ---------------------------------------------------------------------------


class TestCancellationPropagator:
    def _make_chain(self) -> tuple[Cascade, CancellationPropagator]:
        """Create a -> b -> c chain with all nodes READY."""
        cascade = Cascade()
        cascade.add_node(Node(id="a"))
        cascade.add_node(Node(id="b"))
        cascade.add_node(Node(id="c"))
        cascade.add_edge("a", "b", expectation="E1", promise="P1")
        cascade.add_edge("b", "c", expectation="E2", promise="P2")
        # Make b and c READY by completing deps is not needed here —
        # we test cancellation on non-terminal nodes regardless of readiness
        # Force all to READY for simplicity
        for node in cascade.nodes.values():
            node.state = NodeState.READY
        prop = CancellationPropagator(cascade=cascade)
        return cascade, prop

    def test_create_and_get_token(self):
        cascade = Cascade()
        cascade.add_node(Node(id="a"))
        prop = CancellationPropagator(cascade=cascade)
        token = prop.create_token("a")
        assert token is not None
        assert not token.is_cancelled
        assert prop.get_token("a") is token

    def test_get_token_nonexistent(self):
        cascade = Cascade()
        prop = CancellationPropagator(cascade=cascade)
        assert prop.get_token("ghost") is None

    def test_cancel_node_basic(self):
        cascade, prop = self._make_chain()
        prop.create_token("a")
        prop.cancel_node("a", reason="test", cascade=False)
        assert cascade.nodes["a"].state == NodeState.CANCELLED
        assert prop.get_token("a").is_cancelled
        assert cascade.nodes["b"].state == NodeState.READY

    def test_cancel_node_cascades_to_dependents(self):
        cascade, prop = self._make_chain()
        prop.cancel_node("a", reason="root failure", cascade=True)
        assert cascade.nodes["a"].state == NodeState.CANCELLED
        assert cascade.nodes["b"].state == NodeState.CANCELLED
        assert cascade.nodes["c"].state == NodeState.CANCELLED

    def test_cancel_node_skips_completed_and_its_subtree(self):
        """COMPLETED node acts as firewall — cascade does not pass through."""
        cascade, prop = self._make_chain()
        cascade.nodes["b"].state = NodeState.COMPLETED
        prop.cancel_node("a", reason="test", cascade=True)
        assert cascade.nodes["a"].state == NodeState.CANCELLED
        assert cascade.nodes["b"].state == NodeState.COMPLETED
        assert cascade.nodes["c"].state == NodeState.READY

    def test_cancel_node_skips_already_cancelled_subtree(self):
        """Already-CANCELLED node acts as firewall — subtree not revisited."""
        cascade, prop = self._make_chain()
        cascade.nodes["b"].state = NodeState.CANCELLED
        prop.cancel_node("a", reason="test", cascade=True)
        assert cascade.nodes["c"].state == NodeState.READY

    def test_cancel_nonexistent_node(self):
        cascade = Cascade()
        prop = CancellationPropagator(cascade=cascade)
        prop.cancel_node("ghost", reason="test")

    def test_cancel_node_with_token_store(self):
        cascade = Cascade()
        cascade.add_node(Node(id="a", state=NodeState.READY))
        mock_store = MagicMock()
        prop = CancellationPropagator(cascade=cascade, token_store=mock_store)
        prop.cancel_node("a", reason="timeout")
        mock_store.invalidate.assert_called_once_with("a", "timeout")

    def test_cancel_all(self):
        cascade, prop = self._make_chain()
        prop.cancel_all(reason="shutdown")
        for node in cascade.nodes.values():
            assert node.state == NodeState.CANCELLED

    def test_get_cancelled_nodes(self):
        cascade, prop = self._make_chain()
        prop.create_token("a")
        prop.create_token("b")
        prop.cancel_node("a", reason="test", cascade=False)
        cancelled = prop.get_cancelled_nodes()
        assert "a" in cancelled
        assert "b" not in cancelled

    def test_cancel_fires_callback_which_sets_state(self):
        """When token is cancelled via callback, _on_node_cancelled sets state."""
        cascade = Cascade()
        cascade.add_node(Node(id="a", state=NodeState.READY))
        prop = CancellationPropagator(cascade=cascade)
        token = prop.create_token("a")
        token.cancel("external")
        assert cascade.nodes["a"].state == NodeState.CANCELLED

    def test_on_node_cancelled_skips_terminal(self):
        """_on_node_cancelled should not try to cancel already-terminal nodes."""
        cascade = Cascade()
        cascade.add_node(Node(id="a", state=NodeState.READY))
        prop = CancellationPropagator(cascade=cascade)
        prop.create_token("a")

        cascade.nodes["a"].update_state(NodeState.ACTIVE)
        cascade.nodes["a"].update_state(NodeState.COMPLETED)

        prop.node_tokens["a"].cancel("late cancel")
        assert cascade.nodes["a"].state == NodeState.COMPLETED

    def test_on_node_cancelled_handles_failed_state(self):
        """FAILED is terminal — callback should not override it.
        But FAILED -> CANCELLED is valid per state machine. The current
        implementation uses is_terminal() which blocks this."""
        cascade = Cascade()
        cascade.add_node(Node(id="a", state=NodeState.READY))
        prop = CancellationPropagator(cascade=cascade)
        prop.create_token("a")

        cascade.nodes["a"].update_state(NodeState.FAILED)
        prop.node_tokens["a"].cancel("late cancel")
        # is_terminal() blocks FAILED -> CANCELLED, same pattern as replay bug
        assert cascade.nodes["a"].state == NodeState.FAILED


# ---------------------------------------------------------------------------
# Reset operations
# ---------------------------------------------------------------------------


class TestCancellationReset:
    def test_reset_node(self):
        cascade = Cascade()
        cascade.add_node(Node(id="a", state=NodeState.CANCELLED))
        prop = CancellationPropagator(cascade=cascade)
        prop.create_token("a")
        prop.node_tokens["a"].cancel("test")

        prop.reset_node("a")
        assert prop.get_token("a") is None
        assert cascade.nodes["a"].state == NodeState.READY

    def test_reset_node_with_unmet_deps(self):
        """Reset a cancelled node that has unmet deps — should go PENDING."""
        cascade = Cascade()
        cascade.add_node(Node(id="a", state=NodeState.READY))
        cascade.add_node(Node(id="b", state=NodeState.CANCELLED))
        cascade.add_edge("a", "b", expectation="E", promise="P")
        prop = CancellationPropagator(cascade=cascade)

        prop.reset_node("b")
        assert cascade.nodes["b"].state == NodeState.PENDING

    def test_reset_all(self):
        cascade = Cascade()
        cascade.add_node(Node(id="a", state=NodeState.CANCELLED))
        cascade.add_node(Node(id="b", state=NodeState.CANCELLED))
        prop = CancellationPropagator(cascade=cascade)
        prop.create_token("a")
        prop.create_token("b")

        prop.reset_all()
        assert len(prop.node_tokens) == 0
        assert cascade.nodes["a"].state == NodeState.READY
        assert cascade.nodes["b"].state == NodeState.READY


# ---------------------------------------------------------------------------
# Cross-component invariant: cascade cancel consistency
# ---------------------------------------------------------------------------


class TestCancelInvariants:
    def test_fan_out_cancel_reaches_all_branches(self):
        """Cancelling root of a fan-out should cancel all branches."""
        cascade = Cascade()
        cascade.add_node(Node(id="root", state=NodeState.READY))
        for i in range(5):
            nid = f"leaf{i}"
            cascade.add_node(Node(id=nid, state=NodeState.READY))
            cascade.add_edge("root", nid, expectation="E", promise="P")
            cascade.nodes[nid].state = NodeState.READY

        prop = CancellationPropagator(cascade=cascade)
        prop.cancel_node("root", reason="abort", cascade=True)

        for node in cascade.nodes.values():
            assert node.state == NodeState.CANCELLED, (
                f"Node {node.id} should be CANCELLED but is {node.state}"
            )

    def test_diamond_cancel_no_double_cancel(self):
        """Diamond dependency: a -> b, a -> c, b -> d, c -> d.
        Cancelling a should cancel all without errors from double-visiting d."""
        cascade = Cascade()
        for nid in ("a", "b", "c", "d"):
            cascade.add_node(Node(id=nid, state=NodeState.READY))
        cascade.add_edge("a", "b", expectation="E1", promise="P1")
        cascade.add_edge("a", "c", expectation="E2", promise="P2")
        cascade.add_edge("b", "d", expectation="E3", promise="P3")
        cascade.add_edge("c", "d", expectation="E4", promise="P4")
        for node in cascade.nodes.values():
            node.state = NodeState.READY

        prop = CancellationPropagator(cascade=cascade)
        prop.cancel_node("a", reason="abort", cascade=True)

        for node in cascade.nodes.values():
            assert node.state == NodeState.CANCELLED

    def test_cancel_active_node_transitions_correctly(self):
        """ACTIVE -> CANCELLED is valid per state machine."""
        cascade = Cascade()
        cascade.add_node(Node(id="a", state=NodeState.ACTIVE, agent_id="w1"))
        prop = CancellationPropagator(cascade=cascade)
        prop.cancel_node("a", reason="timeout", cascade=False)
        assert cascade.nodes["a"].state == NodeState.CANCELLED
