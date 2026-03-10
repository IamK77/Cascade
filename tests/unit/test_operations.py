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

"""Tests for node operations."""

import pytest

from cascade.core.cascade import Cascade
from cascade.core.node import Node
from cascade.core.state import NodeState
from cascade.operations.add import AddOperation
from cascade.operations.split import SplitOperation
from cascade.operations.remove import RemoveOperation
from cascade.operations.refine import RefineOperation


class TestAddOperation:
    """Tests for AddOperation."""

    def test_add_node(self, empty_cascade):
        """Test adding a node."""
        op = AddOperation(empty_cascade)
        node = Node(id="new", state=NodeState.READY)

        result = op.execute(node)

        assert result.success
        assert "new" in result.affected_nodes
        assert "new" in empty_cascade.nodes

    def test_add_node_with_dependencies(self, empty_cascade):
        """Test adding a node with dependencies."""
        # Add existing nodes
        empty_cascade.add_node(Node(id="dep1", state=NodeState.READY))
        empty_cascade.add_node(Node(id="dep2", state=NodeState.READY))

        op = AddOperation(empty_cascade)
        node = Node(id="new", state=NodeState.PENDING)

        result = op.execute(node, dependencies=["dep1", "dep2"])

        assert result.success
        assert node.in_degree == 2
        assert "new" in empty_cascade.nodes

    def test_add_node_with_dependents(self, empty_cascade):
        """Test adding a node with dependents."""
        # Add existing nodes
        empty_cascade.add_node(Node(id="dep1", state=NodeState.PENDING))

        op = AddOperation(empty_cascade)
        node = Node(id="new", state=NodeState.READY)

        result = op.execute(node, dependents=["dep1"])

        assert result.success
        assert empty_cascade.nodes["dep1"].in_degree == 1

    def test_add_duplicate_node(self, sample_cascade):
        """Test adding duplicate node fails."""
        op = AddOperation(sample_cascade)
        node = Node(id="a", state=NodeState.READY)

        result = op.execute(node)

        assert not result.success
        assert "already exists" in result.message

    def test_add_node_nonexistent_dependency(self, empty_cascade):
        """Test adding node with non-existent dependency fails."""
        op = AddOperation(empty_cascade)
        node = Node(id="new", state=NodeState.PENDING)

        result = op.execute(node, dependencies=["nonexistent"])

        assert not result.success
        assert "not found" in result.message

    def test_add_node_creates_cycle(self, sample_cascade):
        """Test adding node that creates cycle fails."""
        op = AddOperation(sample_cascade)
        node = Node(id="new", state=NodeState.PENDING)

        # Add edge from new to a, and from e to new (creates cycle: a->...->e->new->a)
        result = op.execute(node, dependencies=["e"], dependents=["a"])

        assert not result.success
        assert "cycle" in result.message.lower()


class TestSplitOperation:
    """Tests for SplitOperation."""

    def test_split_node(self, sample_cascade):
        """Test splitting a node."""
        op = SplitOperation(sample_cascade)
        new_nodes = [
            Node(id="a1", state=NodeState.READY),
            Node(id="a2", state=NodeState.PENDING),
        ]

        result = op.split("a", new_nodes)

        assert result.success
        assert "a" not in sample_cascade.nodes
        assert "a1" in sample_cascade.nodes
        assert "a2" in sample_cascade.nodes

    def test_split_transfers_dependencies(self, sample_cascade):
        """Test split transfers parent's dependencies to children."""
        op = SplitOperation(sample_cascade)
        new_nodes = [
            Node(id="a1", state=NodeState.READY),
        ]

        result = op.split("a", new_nodes)

        assert result.success
        # a's dependents (b, c) should now depend on a1
        b_deps = sample_cascade.get_dependencies("b")
        assert any(d.id == "a1" for d in b_deps)

    def test_split_nonexistent_node(self, empty_cascade):
        """Test splitting non-existent node fails."""
        op = SplitOperation(empty_cascade)
        new_nodes = [Node(id="new", state=NodeState.READY)]

        result = op.split("nonexistent", new_nodes)

        assert not result.success
        assert "not found" in result.message

    def test_split_with_id_conflict(self, sample_cascade):
        """Test split with conflicting ID fails."""
        op = SplitOperation(sample_cascade)
        new_nodes = [
            Node(id="b", state=NodeState.PENDING),  # b already exists
        ]

        result = op.split("a", new_nodes)

        assert not result.success
        assert "already exists" in result.message


class TestRemoveOperation:
    """Tests for RemoveOperation."""

    def test_remove_node(self, sample_cascade):
        """Test removing a node."""
        op = RemoveOperation(sample_cascade)

        result = op.remove("c")

        assert result.success
        assert "c" not in sample_cascade.nodes

    def test_remove_nonexistent_node(self, empty_cascade):
        """Test removing non-existent node fails."""
        op = RemoveOperation(empty_cascade)

        result = op.remove("nonexistent")

        assert not result.success
        assert "not found" in result.message

    def test_remove_cascade(self, sample_cascade):
        """Test cascade removal."""
        op = RemoveOperation(sample_cascade)

        result = op.remove("b", cascade=True)

        assert result.success
        assert "b" not in sample_cascade.nodes
        # b's dependents (d, e) should also be removed
        assert "d" not in sample_cascade.nodes
        assert "e" not in sample_cascade.nodes

    def test_remove_without_cascade(self, sample_cascade):
        """Test removal without cascade."""
        op = RemoveOperation(sample_cascade)
        original_len = len(sample_cascade)

        result = op.remove("b", cascade=False)

        assert result.success
        assert "b" not in sample_cascade.nodes
        # d and e should still exist but have updated in_degree
        assert "d" in sample_cascade.nodes
        assert "e" in sample_cascade.nodes
        assert len(sample_cascade) == original_len - 1


class TestRefineOperation:
    """Tests for RefineOperation."""

    def test_refine_node(self, sample_cascade):
        """Test refining a node."""
        op = RefineOperation(sample_cascade)
        new_deps = [
            Node(id="new_dep", state=NodeState.READY),
        ]

        result = op.refine("d", new_deps)

        assert result.success
        assert "new_dep" in sample_cascade.nodes
        # d should now depend on new_dep
        assert sample_cascade.nodes["d"].in_degree > 0

    def test_refine_nonexistent_node(self, empty_cascade):
        """Test refining non-existent node fails."""
        op = RefineOperation(empty_cascade)
        new_deps = [Node(id="new", state=NodeState.READY)]

        result = op.refine("nonexistent", new_deps)

        assert not result.success
        assert "not found" in result.message

    def test_refine_with_id_conflict(self, sample_cascade):
        """Test refine with conflicting ID fails."""
        op = RefineOperation(sample_cascade)
        new_deps = [
            Node(id="a", state=NodeState.READY),  # a already exists
        ]

        result = op.refine("d", new_deps)

        assert not result.success
        assert "already exists" in result.message
