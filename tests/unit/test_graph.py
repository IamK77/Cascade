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


class TestCascadeCreation:
    """Tests for Cascade creation and basic operations."""

    def test_empty_cascade(self, empty_cascade):
        """Test creating an empty Cascade."""
        assert len(empty_cascade) == 0
        assert empty_cascade.nodes == {}

    def test_add_node(self, empty_cascade):
        """Test adding a node."""
        node = Node(id="test", state=NodeState.READY)
        empty_cascade.add_node(node)

        assert "test" in empty_cascade.nodes
        assert len(empty_cascade) == 1

    def test_add_duplicate_node(self, empty_cascade):
        """Test adding duplicate node raises error."""
        node = Node(id="test", state=NodeState.READY)
        empty_cascade.add_node(node)

        with pytest.raises(ValueError, match="already exists"):
            empty_cascade.add_node(node)

    def test_remove_node(self, sample_cascade):
        """Test removing a node."""
        sample_cascade.remove_node("a")

        assert "a" not in sample_cascade.nodes
        assert len(sample_cascade) == 4

    def test_remove_nonexistent_node(self, empty_cascade):
        """Test removing non-existent node raises error."""
        with pytest.raises(ValueError, match="not found"):
            empty_cascade.remove_node("nonexistent")


class TestCascadeEdges:
    """Tests for edge operations."""

    def test_add_edge(self, empty_cascade):
        """Test adding an edge."""
        empty_cascade.add_node(Node(id="a", state=NodeState.READY))
        empty_cascade.add_node(Node(id="b", state=NodeState.PENDING))
        empty_cascade.add_edge("a", "b")

        assert "b" in empty_cascade.adjacency_list["a"]
        assert "a" in empty_cascade.reverse_adjacency["b"]

    def test_add_edge_increments_in_degree(self):
        """Test adding edge increments target's in_degree."""
        cascade = Cascade()
        cascade.add_node(Node(id="a", state=NodeState.READY))
        cascade.add_node(Node(id="b", state=NodeState.READY))
        cascade.add_edge("a", "b")

        assert cascade.nodes["b"].in_degree == 1
        assert cascade.nodes["b"].state == NodeState.PENDING

    def test_add_duplicate_edge(self, sample_cascade):
        """Test adding duplicate edge doesn't duplicate."""
        sample_cascade.add_edge("a", "b")  # Already exists

        # Should not increase in_degree again
        assert sample_cascade.nodes["b"].in_degree == 1

    def test_add_edge_nonexistent_nodes(self, empty_cascade):
        """Test adding edge with non-existent nodes raises error."""
        with pytest.raises(ValueError, match="must exist"):
            empty_cascade.add_edge("a", "b")

    def test_add_edge_creates_cycle(self, sample_cascade):
        """Test adding edge that creates cycle raises error."""
        with pytest.raises(ValueError, match="cycle"):
            sample_cascade.add_edge("e", "a")

    def test_remove_edge(self, sample_cascade):
        """Test removing an edge."""
        sample_cascade.remove_edge("a", "b")

        assert "b" not in sample_cascade.adjacency_list["a"]
        assert "a" not in sample_cascade.reverse_adjacency["b"]
        assert sample_cascade.nodes["b"].in_degree == 0

    def test_get_ready_nodes(self, sample_cascade):
        """Test getting ready nodes."""
        ready = sample_cascade.get_ready_nodes()

        assert len(ready) == 1
        assert ready[0].id == "a"

    def test_get_dependencies(self, sample_cascade):
        """Test getting dependencies."""
        deps = sample_cascade.get_dependencies("d")

        dep_ids = [d.id for d in deps]
        assert "b" in dep_ids

    def test_get_dependents(self, sample_cascade):
        """Test getting dependents."""
        deps = sample_cascade.get_dependents("a")

        dep_ids = [d.id for d in deps]
        assert "b" in dep_ids
        assert "c" in dep_ids


class TestTopologicalSort:
    """Tests for topological sort."""

    def test_topological_sort(self, sample_cascade):
        """Test topological sort ordering."""
        order = sample_cascade.topological_sort()

        assert "a" in order
        assert "b" in order
        assert "c" in order
        assert "d" in order
        assert "e" in order
        assert len(order) == 5

        # a must come before b, c
        assert order.index("a") < order.index("b")
        assert order.index("a") < order.index("c")

        # b must come before d, e
        assert order.index("b") < order.index("d")
        assert order.index("b") < order.index("e")

    def test_topological_sort_cycle(self):
        """Test topological sort with cycle raises error."""
        cascade = Cascade()
        cascade.add_node(Node(id="a", state=NodeState.READY))
        cascade.add_node(Node(id="b", state=NodeState.PENDING))
        cascade.add_edge("a", "b")

        # Manually create cycle by modifying adjacency lists
        cascade.adjacency_list["b"].add("a")
        cascade.reverse_adjacency["a"].add("b")

        with pytest.raises(ValueError, match="cycle"):
            cascade.topological_sort()


class TestCycleDetection:
    """Tests for cycle detection."""

    def test_has_cycle_acyclic(self, sample_cascade):
        """Test has_cycle returns False for acyclic graph."""
        assert not sample_cascade.has_cycle()

    def test_has_cycle_cyclic(self):
        """Test has_cycle returns True for cyclic graph."""
        cascade = Cascade()
        cascade.add_node(Node(id="a", state=NodeState.READY))
        cascade.add_node(Node(id="b", state=NodeState.PENDING))
        cascade.add_edge("a", "b")

        # Adding b -> a would create a cycle, so we manually create it
        cascade.adjacency_list["b"].add("a")
        cascade.reverse_adjacency["a"].add("b")

        assert cascade.has_cycle()

    def test_find_cycle(self):
        """Test finding a cycle."""
        cascade = Cascade()
        cascade.add_node(Node(id="a", state=NodeState.READY))
        cascade.add_node(Node(id="b", state=NodeState.PENDING))
        cascade.add_node(Node(id="c", state=NodeState.PENDING))
        cascade.add_edge("a", "b")
        cascade.add_edge("b", "c")

        # Adding c -> a would create a cycle, so it raises ValueError
        with pytest.raises(ValueError, match="cycle"):
            cascade.add_edge("c", "a")

        # But we can manually create a cycle by modifying adjacency lists
        # to test the find_cycle method
        cascade.adjacency_list["c"].add("a")
        cascade.reverse_adjacency["a"].add("c")

        cycle = cascade.find_cycle()
        assert cycle is not None
        assert len(cycle) == 4  # a -> b -> c -> a

    def test_find_cycle_acyclic(self, sample_cascade):
        """Test find_cycle returns None for acyclic graph."""
        assert sample_cascade.find_cycle() is None

    def test_would_create_cycle(self, sample_cascade):
        """Test checking if edge would create cycle."""
        assert sample_cascade._would_create_cycle("e", "a")
        assert not sample_cascade._would_create_cycle("a", "b")


class TestCascadeRepr:
    """Tests for Cascade string representation."""

    def test_repr(self, sample_cascade):
        """Test Cascade repr."""
        repr_str = repr(sample_cascade)
        assert "Cascade" in repr_str
        assert "nodes=5" in repr_str


class TestGetNodeView:
    """Tests for get_node_view method."""

    def test_get_node_view_basic(self):
        """Test basic node view without context or contracts."""
        cascade = Cascade()
        cascade.add_node(Node(id="a", state=NodeState.READY))

        view = cascade.get_node_view("a")

        assert view["id"] == "a"
        assert view["state"] == "READY"

    def test_get_node_view_not_found(self):
        """Test node view for non-existent node."""
        cascade = Cascade()

        with pytest.raises(ValueError, match="not found"):
            cascade.get_node_view("nonexistent")

    def test_get_node_view_with_contracts(self):
        """Test node view with contracts from edge metadata."""
        from cascade.context.context import Context

        cascade = Cascade()

        node_a = Node(
            id="a",
            state=NodeState.READY,
            context=Context(critical={"project": "test"}, summary="Node A"),
        )
        node_b = Node(
            id="b",
            state=NodeState.PENDING,
        )

        cascade.add_node(node_a)
        cascade.add_node(node_b)
        # Add edge with contract metadata
        cascade.add_edge(
            "a", "b",
            expectation="Expect analysis results",
            promise="Promises to output analysis results",
        )

        # Complete node a (READY -> ACTIVE -> COMPLETED)
        node_a.update_state(NodeState.ACTIVE)
        node_a.update_state(NodeState.COMPLETED)

        # Make b ready
        node_b.decrement_in_degree()
        node_b.update_state(NodeState.READY)

        view = cascade.get_node_view("b")

        assert view["id"] == "b"
        assert view["state"] == "READY"

        # Check context from upstream
        assert "context" in view
        assert view["context"]["critical"] == {"project": "test"}

        # Check contracts
        assert "contracts" in view
        assert len(view["contracts"]) == 1
        assert view["contracts"][0]["node_id"] == "a"
        assert view["contracts"][0]["expectation"] == "Expect analysis results"
        assert view["contracts"][0]["promise"] == "Promises to output analysis results"

    def test_get_node_view_without_promise(self):
        """Test node view without promise."""
        cascade = Cascade()
        cascade.add_node(Node(id="a", state=NodeState.READY))

        view = cascade.get_node_view("a")

        assert view["id"] == "a"
        # promises should not be present if node has no downstream promises
        assert "promises" not in view

    def test_get_node_view_serializable(self):
        """Test that node view is JSON serializable."""
        import json

        from cascade.context.context import Context

        cascade = Cascade()

        node_a = Node(
            id="a",
            state=NodeState.READY,
            context=Context(critical={"key": "value"}, summary="Summary"),
        )
        node_b = Node(id="b", state=NodeState.PENDING)

        cascade.add_node(node_a)
        cascade.add_node(node_b)
        # Add edge with contract metadata
        cascade.add_edge("a", "b", expectation="Expectation", promise="Promise")

        view = cascade.get_node_view("b")

        # Should be serializable
        json_str = json.dumps(view, ensure_ascii=False)
        assert json_str is not None

        # Should be deserializable
        loaded = json.loads(json_str)
        assert loaded["id"] == "b"

    def test_get_node_view_with_visible_descendants(self):
        """Test that node view includes visible descendant nodes."""
        cascade = Cascade()

        # Create a chain: a -> b -> c -> d
        node_a = Node(id="a", state=NodeState.COMPLETED)
        node_b = Node(id="b", state=NodeState.ACTIVE)
        node_c = Node(id="c", state=NodeState.PENDING)
        node_d = Node(id="d", state=NodeState.PENDING)

        cascade.add_node(node_a)
        cascade.add_node(node_b)
        cascade.add_node(node_c)
        cascade.add_node(node_d)

        # Add edges with contract metadata
        cascade.add_edge("a", "b", expectation="Expect output from A", promise="A promises output")
        cascade.add_edge("b", "c", expectation="Expect output from B", promise="B promises output")
        cascade.add_edge("c", "d", expectation="Expect output from C", promise="C promises output")

        # Get view for node b (should see c as child, d as grandchild)
        view = cascade.get_node_view("b")

        assert "visible_nodes" in view
        visible = view["visible_nodes"]

        # Check children (distance 1) - should be node c
        assert "1" in visible
        children = visible["1"]
        assert len(children) == 1
        assert children[0]["id"] == "c"
        assert children[0]["state"] == "PENDING"
        assert "expectations" in children[0]
        assert children[0]["expectations"][0]["node_id"] == "b"
        assert children[0]["expectations"][0]["expectation"] == "Expect output from B"

        # Check grandchildren (distance 2) - should be node d
        assert "2" in visible
        grandchildren = visible["2"]
        assert len(grandchildren) == 1
        assert grandchildren[0]["id"] == "d"
        assert grandchildren[0]["state"] == "PENDING"

    def test_get_node_view_no_descendants(self):
        """Test node view for leaf node with no descendants."""
        cascade = Cascade()

        node = Node(id="leaf", state=NodeState.READY)
        cascade.add_node(node)

        view = cascade.get_node_view("leaf")

        # Should not have visible_nodes if there are no descendants
        assert "visible_nodes" not in view or view.get("visible_nodes") == {}

    def test_get_node_view_multiple_children(self):
        """Test node view with multiple children at same distance."""
        cascade = Cascade()

        # a -> b, a -> c, a -> d
        node_a = Node(id="a", state=NodeState.ACTIVE)
        node_b = Node(id="b", state=NodeState.PENDING)
        node_c = Node(id="c", state=NodeState.PENDING)
        node_d = Node(id="d", state=NodeState.PENDING)

        cascade.add_node(node_a)
        cascade.add_node(node_b)
        cascade.add_node(node_c)
        cascade.add_node(node_d)

        # Add edges with contract metadata
        cascade.add_edge("a", "b", expectation="Expect from A", promise="A promises")
        cascade.add_edge("a", "c", expectation="Expect from A", promise="A promises")
        cascade.add_edge("a", "d", expectation="Expect from A", promise="A promises")

        view = cascade.get_node_view("a")

        assert "visible_nodes" in view
        children = view["visible_nodes"]["1"]

        # Should have 3 children
        assert len(children) == 3
        child_ids = {c["id"] for c in children}
        assert child_ids == {"b", "c", "d"}

    def test_get_node_view_with_promises(self):
        """Test node view includes promises to dependents."""
        cascade = Cascade()

        node_a = Node(id="a", state=NodeState.READY)
        node_b = Node(id="b", state=NodeState.PENDING)

        cascade.add_node(node_a)
        cascade.add_node(node_b)
        cascade.add_edge("a", "b", promise="Promise to output data")

        view = cascade.get_node_view("a")

        # Node a should have promises to its dependents
        assert "promises" in view
        assert len(view["promises"]) == 1
        assert view["promises"][0]["to_node"] == "b"
        assert view["promises"][0]["promise"] == "Promise to output data"


class TestGraphConnectivity:
    """Tests for graph connectivity (single DAG requirement)."""

    def test_empty_graph_is_connected(self, empty_cascade):
        """Test empty graph is considered connected."""
        assert empty_cascade.is_connected()

    def test_single_node_is_connected(self):
        """Test single node graph is connected."""
        cascade = Cascade()
        cascade.add_node(Node(id="a", state=NodeState.READY))
        assert cascade.is_connected()

    def test_linear_chain_is_connected(self):
        """Test linear chain is connected."""
        cascade = Cascade()
        cascade.add_node(Node(id="a", state=NodeState.READY))
        cascade.add_node(Node(id="b", state=NodeState.PENDING))
        cascade.add_node(Node(id="c", state=NodeState.PENDING))
        cascade.add_edge("a", "b")
        cascade.add_edge("b", "c")
        assert cascade.is_connected()

    def test_diamond_shape_is_connected(self):
        """Test diamond shape graph is connected."""
        #     a
        #    / \
        #   b   c
        #    \ /
        #     d
        cascade = Cascade()
        cascade.add_node(Node(id="a", state=NodeState.READY))
        cascade.add_node(Node(id="b", state=NodeState.PENDING))
        cascade.add_node(Node(id="c", state=NodeState.PENDING))
        cascade.add_node(Node(id="d", state=NodeState.PENDING))
        cascade.add_edge("a", "b")
        cascade.add_edge("a", "c")
        cascade.add_edge("b", "d")
        cascade.add_edge("c", "d")
        assert cascade.is_connected()

    def test_disconnected_graph_not_connected(self):
        """Test graph with disconnected components."""
        cascade = Cascade()
        # First component: a -> b
        cascade.add_node(Node(id="a", state=NodeState.READY))
        cascade.add_node(Node(id="b", state=NodeState.PENDING))
        cascade.add_edge("a", "b")

        # Second component: c -> d (manually add without connecting to a, b)
        cascade.add_node(Node(id="c", state=NodeState.READY))
        cascade.add_node(Node(id="d", state=NodeState.PENDING))
        # Manually create edge without incrementing in_degree to simulate disconnected
        cascade.adjacency_list["c"].add("d")
        cascade.reverse_adjacency["d"].add("c")

        assert not cascade.is_connected()

    def test_sample_cascade_is_connected(self, sample_cascade):
        """Test sample_cascade fixture is connected."""
        assert sample_cascade.is_connected()
