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
from cascade.context.cancellation import (
    CancellationPropagator,
    CancellationToken,
    CancelledError,
)
from cascade.context.context import Context
from cascade.context.propagator import ContextPropagator


class TestContext:
    """Tests for Context class."""

    def test_context_creation(self):
        context = Context()
        assert context.critical == {}
        assert context.summary == ""
        assert context.artifacts == ""

    def test_context_with_values(self, sample_context):
        assert "key1" in sample_context.critical
        assert sample_context.summary == "This is a summary"
        assert "Full Artifacts" in sample_context.artifacts

    def test_set_critical(self):
        context = Context()
        context.set_critical("key", "value")
        assert context.critical["key"] == "value"

    def test_get_critical(self):
        context = Context(critical={"key": "value"})
        assert context.get_critical("key") == "value"
        assert context.get_critical("missing") is None
        assert context.get_critical("missing", "default") == "default"

    def test_describe(self):
        context = Context(critical={"key": "value"}, summary="A summary")
        desc = context.describe()
        assert "Context" in desc
        assert "Critical" in desc
        assert "key" in desc
        assert "Summary" in desc


class TestContextPropagator:
    """Tests for ContextPropagator."""

    def test_collect_context_at(self, sample_cascade_with_context):
        propagator = ContextPropagator(sample_cascade_with_context)
        entries = propagator.collect_context_at("b")
        assert len(entries) == 1
        assert entries[0].node_id == "a"
        assert entries[0].distance == 1
        assert entries[0].path == ["a"]
        assert entries[0].expectation == "Expect output from a"
        assert entries[0].promise == "A promises output"
        assert entries[0].critical["project"] == "test"
        assert entries[0].summary == "Initial task"

    def test_collect_no_ancestors(self):
        cascade = Cascade()
        cascade.add_node(Node(id="root", state=NodeState.READY))
        propagator = ContextPropagator(cascade)
        entries = propagator.collect_context_at("root")
        assert entries == []

    def test_collect_summary_limited_by_distance(self):
        """Summary stops propagating beyond SUMMARY_MAX_DISTANCE."""
        cascade = Cascade()
        ctx = Context(critical={"k": "v"}, summary="grandparent summary")
        cascade.add_node(Node(id="a", state=NodeState.COMPLETED, context=ctx))
        cascade.add_node(Node(id="b", state=NodeState.COMPLETED))
        cascade.add_node(Node(id="c", state=NodeState.PENDING))
        cascade.add_edge("a", "b", expectation="E", promise="P1")
        cascade.add_edge("b", "c", expectation="E", promise="P2")

        propagator = ContextPropagator(cascade)
        entries = propagator.collect_context_at("c")
        a_entry = next(e for e in entries if e.node_id == "a")
        assert a_entry.distance == 2
        assert a_entry.path == ["a", "b"]
        assert a_entry.summary == "grandparent summary"
        assert a_entry.critical["k"] == "v"
        assert a_entry.expectation == ""

    def test_collect_diamond_no_overwrite(self):
        """Fan-in: B and C both set same critical key — both preserved."""
        cascade = Cascade()
        cascade.add_node(
            Node(id="b", state=NodeState.COMPLETED, context=Context(critical={"branch": "B"}))
        )
        cascade.add_node(
            Node(id="c", state=NodeState.COMPLETED, context=Context(critical={"branch": "C"}))
        )
        cascade.add_node(Node(id="d", state=NodeState.PENDING))
        cascade.add_edge("b", "d", expectation="Eb", promise="B output")
        cascade.add_edge("c", "d", expectation="Ec", promise="C output")

        propagator = ContextPropagator(cascade)
        entries = propagator.collect_context_at("d")
        branches = {e.critical["branch"] for e in entries}
        assert branches == {"B", "C"}
        for e in entries:
            assert e.distance == 1
            assert e.expectation != ""


class TestCancellationToken:
    """Tests for CancellationToken."""

    def test_token_not_cancelled_initially(self):
        token = CancellationToken()
        assert not token.is_cancelled
        assert token.reason is None
        assert bool(token) is True

    def test_cancel_token(self):
        token = CancellationToken()
        token.cancel("Test reason")
        assert token.is_cancelled
        assert token.reason == "Test reason"
        assert bool(token) is False

    def test_throw_if_cancelled(self):
        token = CancellationToken()
        token.cancel()
        with pytest.raises(CancelledError):
            token.throw_if_cancelled()

    def test_throw_if_cancelled_not_raises(self):
        token = CancellationToken()
        token.throw_if_cancelled()

    def test_register_callback(self):
        token = CancellationToken()
        called = []
        token.register_callback(lambda: called.append(True))
        assert not called
        token.cancel()
        assert called == [True]

    def test_callback_on_already_cancelled(self):
        token = CancellationToken()
        token.cancel()
        called = []
        token.register_callback(lambda: called.append(True))
        assert called == [True]

    def test_unregister_callback(self):
        token = CancellationToken()
        called = []

        def callback():
            called.append(True)

        unregister = token.register_callback(callback)
        unregister()
        token.cancel()
        assert not called

    def test_async_event(self):
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
        cascade = Cascade()
        cascade.add_node(Node(id="test", state=NodeState.READY))
        propagator = CancellationPropagator(cascade)
        token = propagator.create_token("test")
        assert token is not None
        assert propagator.get_token("test") is token

    def test_cancel_node(self):
        cascade = Cascade()
        cascade.add_node(Node(id="a", state=NodeState.READY))
        cascade.add_node(Node(id="b", state=NodeState.PENDING))
        cascade.add_edge("a", "b", expectation="Expect from a", promise="Promise to b")

        propagator = CancellationPropagator(cascade)
        propagator.cancel_node("a")
        assert cascade.nodes["a"].state.name == "CANCELLED"

    def test_cancel_cascade(self):
        cascade = Cascade()
        cascade.add_node(Node(id="a", state=NodeState.READY))
        cascade.add_node(Node(id="b", state=NodeState.PENDING))
        cascade.add_edge("a", "b", expectation="Expect from a", promise="Promise to b")

        propagator = CancellationPropagator(cascade)
        propagator.cancel_node("a", cascade=True)
        assert cascade.nodes["a"].state.name == "CANCELLED"
        assert cascade.nodes["b"].state.name == "CANCELLED"

    def test_reset_node(self):
        cascade = Cascade()
        cascade.add_node(Node(id="test", state=NodeState.READY))

        propagator = CancellationPropagator(cascade)
        token = propagator.create_token("test")
        token.cancel()

        propagator.reset_node("test")
        assert propagator.get_token("test") is None
        assert cascade.nodes["test"].state == NodeState.READY
