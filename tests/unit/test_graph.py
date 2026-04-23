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

"""Tests for Cascade class."""

import pytest

from cascade.core.cascade import Cascade
from cascade.core.node import Node
from cascade.core.state import NodeState
from cascade.types import Context, Contract
from cascade.view import get_node_view


def make_contract(from_id: str, to_id: str) -> tuple[str, str]:
    """Helper to create contract strings for tests."""
    return (f"Expect from {from_id}", f"Promise to {to_id}")


class TestCascadeCreation:
    """Tests for Cascade creation and basic operations."""

    def test_empty_cascade(self, empty_cascade):
        assert len(empty_cascade) == 0
        assert empty_cascade.nodes == {}

    def test_add_node(self, empty_cascade):
        node = Node(id="test", state=NodeState.READY)
        empty_cascade.add_node(node)
        assert "test" in empty_cascade.nodes
        assert len(empty_cascade) == 1

    def test_add_duplicate_node(self, empty_cascade):
        node = Node(id="test", state=NodeState.READY)
        empty_cascade.add_node(node)
        with pytest.raises(ValueError, match="already exists"):
            empty_cascade.add_node(node)

    def test_remove_node(self, sample_cascade):
        sample_cascade.remove_node("a")
        assert "a" not in sample_cascade.nodes
        assert len(sample_cascade) == 4

    def test_remove_nonexistent_node(self, empty_cascade):
        with pytest.raises(ValueError, match="not found"):
            empty_cascade.remove_node("nonexistent")


class TestCascadeEdges:
    """Tests for edge operations."""

    def test_add_edge(self, empty_cascade):
        empty_cascade.add_node(Node(id="a", state=NodeState.READY))
        empty_cascade.add_node(Node(id="b", state=NodeState.PENDING))
        exp, prom = make_contract("a", "b")
        empty_cascade.add_edge("a", "b", expectation=exp, promise=prom)

        assert "b" in empty_cascade._adjacency["a"]
        assert "a" in empty_cascade._reverse["b"]

    def test_add_edge_updates_readiness(self):
        """Test that adding edge changes READY node to PENDING."""
        cascade = Cascade()
        cascade.add_node(Node(id="a", state=NodeState.READY))
        cascade.add_node(Node(id="b", state=NodeState.READY))
        exp, prom = make_contract("a", "b")
        cascade.add_edge("a", "b", expectation=exp, promise=prom)

        # b should now be PENDING (has uncompleted dependency a)
        assert cascade.nodes["b"].state == NodeState.PENDING
        assert cascade.pending_dependency_count("b") == 1

    def test_add_edge_with_contract_object(self):
        """Test adding edge with a Contract object."""
        cascade = Cascade()
        cascade.add_node(Node(id="a", state=NodeState.READY))
        cascade.add_node(Node(id="b", state=NodeState.READY))

        contract = Contract(expectation="Need data", promise="Will provide data")
        cascade.add_edge("a", "b", contract=contract)

        retrieved = cascade.get_contract("a", "b")
        assert retrieved is not None
        assert retrieved.expectation == "Need data"
        assert retrieved.promise == "Will provide data"

    def test_add_duplicate_edge(self, sample_cascade):
        exp, prom = make_contract("a", "b")
        sample_cascade.add_edge("a", "b", expectation=exp, promise=prom)

        # Should not change pending count
        assert sample_cascade.pending_dependency_count("b") == 1

    def test_add_edge_nonexistent_nodes(self, empty_cascade):
        exp, prom = make_contract("a", "b")
        with pytest.raises(ValueError, match="must exist"):
            empty_cascade.add_edge("a", "b", expectation=exp, promise=prom)

    def test_add_edge_creates_cycle(self, sample_cascade):
        exp, prom = make_contract("e", "a")
        with pytest.raises(ValueError, match="cycle"):
            sample_cascade.add_edge("e", "a", expectation=exp, promise=prom)

    def test_add_edge_missing_expectation(self):
        cascade = Cascade()
        cascade.add_node(Node(id="a", state=NodeState.READY))
        cascade.add_node(Node(id="b", state=NodeState.READY))
        with pytest.raises(ValueError, match="expectation is required"):
            cascade.add_edge("a", "b", expectation="", promise="some promise")

    def test_add_edge_missing_promise(self):
        cascade = Cascade()
        cascade.add_node(Node(id="a", state=NodeState.READY))
        cascade.add_node(Node(id="b", state=NodeState.READY))
        with pytest.raises(ValueError, match="promise is required"):
            cascade.add_edge("a", "b", expectation="some expectation", promise="")

    def test_remove_edge(self, sample_cascade):
        sample_cascade.remove_edge("a", "b")
        assert "b" not in sample_cascade._adjacency["a"]
        assert "a" not in sample_cascade._reverse["b"]

    def test_get_ready_nodes(self, sample_cascade):
        ready = sample_cascade.get_ready_nodes()
        assert len(ready) == 1
        assert ready[0].id == "a"

    def test_get_dependencies(self, sample_cascade):
        deps = sample_cascade.get_dependencies("d")
        dep_ids = [d.id for d in deps]
        assert "b" in dep_ids

    def test_get_dependents(self, sample_cascade):
        deps = sample_cascade.get_dependents("a")
        dep_ids = [d.id for d in deps]
        assert "b" in dep_ids
        assert "c" in dep_ids


class TestPendingDependencyCount:
    """Tests for the computed pending_dependency_count."""

    def test_no_dependencies(self):
        cascade = Cascade()
        cascade.add_node(Node(id="a", state=NodeState.READY))
        assert cascade.pending_dependency_count("a") == 0

    def test_with_uncompleted_dependency(self):
        cascade = Cascade()
        cascade.add_node(Node(id="a", state=NodeState.READY))
        cascade.add_node(Node(id="b", state=NodeState.PENDING))
        cascade.add_edge("a", "b", expectation="E", promise="P")
        assert cascade.pending_dependency_count("b") == 1

    def test_with_completed_dependency(self):
        cascade = Cascade()
        cascade.add_node(Node(id="a", state=NodeState.COMPLETED))
        cascade.add_node(Node(id="b", state=NodeState.READY))
        cascade.add_edge("a", "b", expectation="E", promise="P")
        assert cascade.pending_dependency_count("b") == 0

    def test_notify_completion_unblocks(self):
        cascade = Cascade()
        cascade.add_node(Node(id="a", state=NodeState.READY))
        cascade.add_node(Node(id="b", state=NodeState.PENDING))
        cascade.add_edge("a", "b", expectation="E", promise="P")

        # Complete a
        cascade.nodes["a"].state = NodeState.COMPLETED
        unblocked = cascade.notify_completion("a")

        assert "b" in unblocked
        assert cascade.nodes["b"].state == NodeState.READY


class TestTopologicalSort:
    """Tests for topological sort."""

    def test_topological_sort(self, sample_cascade):
        order = sample_cascade.topological_sort()
        assert len(order) == 5
        assert order.index("a") < order.index("b")
        assert order.index("a") < order.index("c")
        assert order.index("b") < order.index("d")
        assert order.index("b") < order.index("e")

    def test_topological_sort_cycle(self):
        cascade = Cascade()
        cascade.add_node(Node(id="a", state=NodeState.READY))
        cascade.add_node(Node(id="b", state=NodeState.PENDING))
        exp, prom = make_contract("a", "b")
        cascade.add_edge("a", "b", expectation=exp, promise=prom)

        # Manually create cycle
        cascade._adjacency["b"].add("a")
        cascade._reverse["a"].add("b")

        with pytest.raises(ValueError, match="cycle"):
            cascade.topological_sort()


class TestCycleDetection:
    """Tests for cycle detection."""

    def test_has_cycle_acyclic(self, sample_cascade):
        assert not sample_cascade.has_cycle()

    def test_has_cycle_cyclic(self):
        cascade = Cascade()
        cascade.add_node(Node(id="a", state=NodeState.READY))
        cascade.add_node(Node(id="b", state=NodeState.PENDING))
        exp, prom = make_contract("a", "b")
        cascade.add_edge("a", "b", expectation=exp, promise=prom)

        cascade._adjacency["b"].add("a")
        cascade._reverse["a"].add("b")
        assert cascade.has_cycle()

    def test_find_cycle(self):
        cascade = Cascade()
        cascade.add_node(Node(id="a", state=NodeState.READY))
        cascade.add_node(Node(id="b", state=NodeState.PENDING))
        cascade.add_node(Node(id="c", state=NodeState.PENDING))
        exp1, prom1 = make_contract("a", "b")
        exp2, prom2 = make_contract("b", "c")
        cascade.add_edge("a", "b", expectation=exp1, promise=prom1)
        cascade.add_edge("b", "c", expectation=exp2, promise=prom2)

        exp3, prom3 = make_contract("c", "a")
        with pytest.raises(ValueError, match="cycle"):
            cascade.add_edge("c", "a", expectation=exp3, promise=prom3)

        cascade._adjacency["c"].add("a")
        cascade._reverse["a"].add("c")

        cycle = cascade.find_cycle()
        assert cycle is not None
        assert len(cycle) == 4

    def test_find_cycle_acyclic(self, sample_cascade):
        assert sample_cascade.find_cycle() is None

    def test_would_create_cycle(self, sample_cascade):
        assert sample_cascade._would_create_cycle("e", "a")
        assert not sample_cascade._would_create_cycle("a", "b")


class TestCascadeRepr:
    def test_repr(self, sample_cascade):
        repr_str = repr(sample_cascade)
        assert "Cascade" in repr_str
        assert "nodes=5" in repr_str


class TestGetNodeView:
    """Tests for get_node_view function."""

    def test_get_node_view_basic(self):
        cascade = Cascade()
        cascade.add_node(Node(id="a", state=NodeState.READY))
        view = get_node_view(cascade,"a")
        assert view["id"] == "a"
        assert view["state"] == "READY"

    def test_get_node_view_not_found(self):
        cascade = Cascade()
        with pytest.raises(ValueError, match="not found"):
            get_node_view(cascade,"nonexistent")

    def test_get_node_view_with_contracts(self):
        cascade = Cascade()

        node_a = Node(
            id="a", state=NodeState.READY,
            context=Context(critical={"project": "test"}, summary="Node A"),
        )
        node_b = Node(id="b", state=NodeState.PENDING)

        cascade.add_node(node_a)
        cascade.add_node(node_b)
        cascade.add_edge("a", "b", expectation="Expect analysis results", promise="Promises to output analysis results")

        node_a.update_state(NodeState.ACTIVE)
        node_a.update_state(NodeState.COMPLETED)

        # Notify completion to unblock b
        cascade.notify_completion("a")

        view = get_node_view(cascade,"b")
        assert view["id"] == "b"
        assert view["state"] == "READY"
        assert "upstream" in view
        assert len(view["upstream"]) == 1
        entry = view["upstream"][0]
        assert entry["node_id"] == "a"
        assert entry["distance"] == 1
        assert entry["expectation"] == "Expect analysis results"
        assert entry["promise"] == "Promises to output analysis results"
        assert entry["delivered"]["critical"] == {"project": "test"}

    def test_get_node_view_without_promise(self):
        cascade = Cascade()
        cascade.add_node(Node(id="a", state=NodeState.READY))
        view = get_node_view(cascade,"a")
        assert view["id"] == "a"
        assert "promises" not in view

    def test_get_node_view_serializable(self):
        import json

        cascade = Cascade()
        node_a = Node(id="a", state=NodeState.READY, context=Context(critical={"key": "value"}, summary="Summary"))
        node_b = Node(id="b", state=NodeState.PENDING)
        cascade.add_node(node_a)
        cascade.add_node(node_b)
        cascade.add_edge("a", "b", expectation="Expectation", promise="Promise")

        view = get_node_view(cascade,"b")
        json_str = json.dumps(view, ensure_ascii=False)
        loaded = json.loads(json_str)
        assert loaded["id"] == "b"

    def test_get_node_view_with_visible_descendants(self):
        cascade = Cascade()

        cascade.add_node(Node(id="a", state=NodeState.COMPLETED))
        cascade.add_node(Node(id="b", state=NodeState.ACTIVE))
        cascade.add_node(Node(id="c", state=NodeState.PENDING))
        cascade.add_node(Node(id="d", state=NodeState.PENDING))

        cascade.add_edge("a", "b", expectation="Expect output from A", promise="A promises output")
        cascade.add_edge("b", "c", expectation="Expect output from B", promise="B promises output")
        cascade.add_edge("c", "d", expectation="Expect output from C", promise="C promises output")

        view = get_node_view(cascade,"b")
        assert "visible_nodes" in view
        visible = view["visible_nodes"]
        assert "1" in visible
        assert len(visible["1"]) == 1
        assert visible["1"][0]["id"] == "c"
        assert "2" in visible
        assert visible["2"][0]["id"] == "d"

    def test_get_node_view_no_descendants(self):
        cascade = Cascade()
        cascade.add_node(Node(id="leaf", state=NodeState.READY))
        view = get_node_view(cascade,"leaf")
        assert "visible_nodes" not in view or view.get("visible_nodes") == {}

    def test_get_node_view_multiple_children(self):
        cascade = Cascade()
        cascade.add_node(Node(id="a", state=NodeState.ACTIVE))
        cascade.add_node(Node(id="b", state=NodeState.PENDING))
        cascade.add_node(Node(id="c", state=NodeState.PENDING))
        cascade.add_node(Node(id="d", state=NodeState.PENDING))

        cascade.add_edge("a", "b", expectation="Expect from A", promise="A promises")
        cascade.add_edge("a", "c", expectation="Expect from A", promise="A promises")
        cascade.add_edge("a", "d", expectation="Expect from A", promise="A promises")

        view = get_node_view(cascade,"a")
        assert "visible_nodes" in view
        children = view["visible_nodes"]["1"]
        assert len(children) == 3
        child_ids = {c["id"] for c in children}
        assert child_ids == {"b", "c", "d"}

    def test_get_node_view_with_promises(self):
        cascade = Cascade()
        cascade.add_node(Node(id="a", state=NodeState.READY))
        cascade.add_node(Node(id="b", state=NodeState.PENDING))
        cascade.add_edge("a", "b", expectation="Expect data", promise="Promise to output data")

        view = get_node_view(cascade,"a")
        assert "promises" in view
        assert len(view["promises"]) == 1
        assert view["promises"][0]["to_node"] == "b"
        assert view["promises"][0]["promise"] == "Promise to output data"


class TestGraphConnectivity:
    """Tests for graph connectivity."""

    def test_empty_graph_is_connected(self, empty_cascade):
        assert empty_cascade.is_connected()

    def test_single_node_is_connected(self):
        cascade = Cascade()
        cascade.add_node(Node(id="a", state=NodeState.READY))
        assert cascade.is_connected()

    def test_linear_chain_is_connected(self):
        cascade = Cascade()
        cascade.add_node(Node(id="a", state=NodeState.READY))
        cascade.add_node(Node(id="b", state=NodeState.PENDING))
        cascade.add_node(Node(id="c", state=NodeState.PENDING))
        cascade.add_edge("a", "b", expectation="E1", promise="P1")
        cascade.add_edge("b", "c", expectation="E2", promise="P2")
        assert cascade.is_connected()

    def test_diamond_shape_is_connected(self):
        cascade = Cascade()
        cascade.add_node(Node(id="a", state=NodeState.READY))
        cascade.add_node(Node(id="b", state=NodeState.PENDING))
        cascade.add_node(Node(id="c", state=NodeState.PENDING))
        cascade.add_node(Node(id="d", state=NodeState.PENDING))
        cascade.add_edge("a", "b", expectation="E", promise="P")
        cascade.add_edge("a", "c", expectation="E", promise="P")
        cascade.add_edge("b", "d", expectation="E", promise="P")
        cascade.add_edge("c", "d", expectation="E", promise="P")
        assert cascade.is_connected()

    def test_disconnected_graph_not_connected(self):
        cascade = Cascade()
        cascade.add_node(Node(id="a", state=NodeState.READY))
        cascade.add_node(Node(id="b", state=NodeState.PENDING))
        cascade.add_edge("a", "b", expectation="E", promise="P")

        cascade.add_node(Node(id="c", state=NodeState.READY))
        cascade.add_node(Node(id="d", state=NodeState.PENDING))
        cascade._adjacency["c"].add("d")
        cascade._reverse["d"].add("c")

        assert not cascade.is_connected()

    def test_sample_cascade_is_connected(self, sample_cascade):
        assert sample_cascade.is_connected()
