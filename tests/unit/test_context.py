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

"""Tests for Context class and propagation."""

import pytest

from cascade import Cascade, Node, NodeState
from cascade.context.context import Context
from cascade.context.propagator import ContextPropagator, PropagationResult
from cascade.context.cancellation import (
    CancellationToken,
    CancelledError,
    CancellationPropagator,
)
from cascade.protocols.context_protocol import ContextLevel


class TestContext:
    """Tests for Context class."""

    def test_context_creation(self):
        """Test creating a context."""
        context = Context()

        assert context.critical == {}
        assert context.summary == ""
        assert context.artifacts == ""

    def test_context_with_values(self, sample_context):
        """Test context with initial values."""
        assert "key1" in sample_context.critical
        assert sample_context.summary == "This is a summary"
        assert "Full Artifacts" in sample_context.artifacts

    def test_propagate_to_critical(self):
        """Test critical propagates indefinitely."""
        context = Context(critical={"data": "value"})

        assert context.propagate_to(ContextLevel.CRITICAL, distance=0)
        assert context.propagate_to(ContextLevel.CRITICAL, distance=100)

    def test_propagate_to_summary(self):
        """Test summary propagates to grandchildren."""
        context = Context(summary="test")

        assert context.propagate_to(ContextLevel.SUMMARY, distance=0)
        assert context.propagate_to(ContextLevel.SUMMARY, distance=1)
        assert context.propagate_to(ContextLevel.SUMMARY, distance=2)
        assert not context.propagate_to(ContextLevel.SUMMARY, distance=3)

    def test_propagate_to_artifacts(self):
        """Test artifacts path pointer always propagates."""
        # Artifacts stores a file path pointer which should always propagate
        context = Context(artifacts=".cascadeartifacts/node_a.md")

        assert context.propagate_to(ContextLevel.ARTIFACTS, distance=0)
        assert context.propagate_to(ContextLevel.ARTIFACTS, distance=1)
        assert context.propagate_to(ContextLevel.ARTIFACTS, distance=100)

    def test_merge_contexts(self):
        """Test merging contexts."""
        ctx1 = Context(critical={"a": 1}, summary="Summary 1")
        ctx2 = Context(critical={"b": 2}, summary="Summary 2")

        merged = ctx1.merge(ctx2)

        assert merged.critical == {"a": 1, "b": 2}
        assert "Summary 1" in merged.summary
        assert "Summary 2" in merged.summary

    def test_set_critical(self):
        """Test setting critical values."""
        context = Context()
        context.set_critical("key", "value")

        assert context.critical["key"] == "value"

    def test_get_critical(self):
        """Test getting critical values."""
        context = Context(critical={"key": "value"})

        assert context.get_critical("key") == "value"
        assert context.get_critical("missing") is None
        assert context.get_critical("missing", "default") == "default"

    def test_describe(self):
        """Test context description."""
        context = Context(
            critical={"key": "value"},
            summary="A summary"
        )

        desc = context.describe()
        assert "Context" in desc
        assert "Critical" in desc
        assert "key" in desc
        assert "Summary" in desc


class TestContextPropagator:
    """Tests for ContextPropagator."""

    def test_propagate_from(self, sample_cascade_with_context):
        """Test propagating from a source node."""
        propagator = ContextPropagator(sample_cascade_with_context)
        source_context = sample_cascade_with_context.nodes["a"].context

        result = propagator.propagate_from("a", source_context)

        assert "a" in result.reached_nodes
        assert "b" in result.reached_nodes

    def test_propagate_to_ancestors(self, sample_cascade_with_context):
        """Test propagating to ancestors."""
        propagator = ContextPropagator(sample_cascade_with_context)
        target_context = sample_cascade_with_context.nodes["b"].context

        result = propagator.propagate_to_ancestors("b", target_context)

        assert "b" in result.reached_nodes
        assert "a" in result.reached_nodes

    def test_collect_context_at(self, sample_cascade_with_context):
        """Test collecting context at a node."""
        propagator = ContextPropagator(sample_cascade_with_context)

        context = propagator.collect_context_at("b", max_distance=2)

        # Should have critical from both a and b
        assert "project" in context.critical
        assert "depends_on" in context.critical

    def test_propagate_max_distance(self, sample_cascade_with_context):
        """Test propagation with max distance."""
        propagator = ContextPropagator(sample_cascade_with_context)
        source_context = sample_cascade_with_context.nodes["a"].context

        result = propagator.propagate_from("a", source_context, max_distance=0)

        assert "a" in result.reached_nodes
        assert "b" not in result.reached_nodes

    def test_propagation_result_get_nodes_at_distance(self, sample_cascade_with_context):
        """Test getting nodes at specific distance."""
        propagator = ContextPropagator(sample_cascade_with_context)
        source_context = sample_cascade_with_context.nodes["a"].context

        result = propagator.propagate_from("a", source_context)

        distance_0 = result.get_nodes_at_distance(0)
        distance_1 = result.get_nodes_at_distance(1)

        assert "a" in distance_0
        assert "b" in distance_1


class TestCancellationToken:
    """Tests for CancellationToken."""

    def test_token_not_cancelled_initially(self):
        """Test token starts not cancelled."""
        token = CancellationToken()

        assert not token.is_cancelled
        assert token.reason is None
        assert bool(token) is True

    def test_cancel_token(self):
        """Test cancelling a token."""
        token = CancellationToken()
        token.cancel("Test reason")

        assert token.is_cancelled
        assert token.reason == "Test reason"
        assert bool(token) is False

    def test_throw_if_cancelled(self):
        """Test throw_if_cancelled raises when cancelled."""
        token = CancellationToken()
        token.cancel()

        with pytest.raises(CancelledError):
            token.throw_if_cancelled()

    def test_throw_if_cancelled_not_raises(self):
        """Test throw_if_cancelled doesn't raise when not cancelled."""
        token = CancellationToken()

        # Should not raise
        token.throw_if_cancelled()

    def test_register_callback(self):
        """Test registering cancellation callback."""
        token = CancellationToken()
        called = []

        def callback():
            called.append(True)

        token.register_callback(callback)
        assert not called

        token.cancel()
        assert called == [True]

    def test_callback_on_already_cancelled(self):
        """Test callback called immediately if already cancelled."""
        token = CancellationToken()
        token.cancel()
        called = []

        def callback():
            called.append(True)

        token.register_callback(callback)
        assert called == [True]

    def test_unregister_callback(self):
        """Test unregistering a callback."""
        token = CancellationToken()
        called = []

        def callback():
            called.append(True)

        unregister = token.register_callback(callback)
        unregister()
        token.cancel()

        assert not called

    def test_async_event(self):
        """Test async event is set on cancellation."""
        import asyncio

        async def test():
            token = CancellationToken()
            event = token.get_event()

            assert not event.is_set()

            token.cancel()
            assert event.is_set()

        asyncio.run(test())


class TestCancellationPropagator:
    """Tests for CancellationPropagator."""

    def test_create_token(self):
        """Test creating a token for a node."""
        cascade = Cascade()
        cascade.add_node(Node(id="test", state=NodeState.READY))

        propagator = CancellationPropagator(cascade)
        token = propagator.create_token("test")

        assert token is not None
        assert propagator.get_token("test") is token

    def test_cancel_node(self):
        """Test cancelling a node."""
        from cascade.core.node import Node

        cascade = Cascade()
        cascade.add_node(Node(id="a", state=NodeState.READY))
        cascade.add_node(Node(id="b", state=NodeState.PENDING))
        cascade.add_edge("a", "b")

        propagator = CancellationPropagator(cascade)
        propagator.cancel_node("a")

        assert cascade.nodes["a"].state.name == "CANCELLED"

    def test_cancel_cascade(self):
        """Test cascade cancellation."""
        from cascade.core.node import Node

        cascade = Cascade()
        cascade.add_node(Node(id="a", state=NodeState.READY))
        cascade.add_node(Node(id="b", state=NodeState.PENDING))
        cascade.add_edge("a", "b")

        propagator = CancellationPropagator(cascade)
        propagator.cancel_node("a", cascade=True)

        # Both should be cancelled
        assert cascade.nodes["a"].state.name == "CANCELLED"
        assert cascade.nodes["b"].state.name == "CANCELLED"

    def test_reset_node(self):
        """Test resetting a cancelled node."""
        from cascade.core.node import Node

        cascade = Cascade()
        cascade.add_node(Node(id="test", state=NodeState.READY))

        propagator = CancellationPropagator(cascade)
        token = propagator.create_token("test")
        token.cancel()

        propagator.reset_node("test")

        assert propagator.get_token("test") is None
        assert cascade.nodes["test"].state == NodeState.READY
