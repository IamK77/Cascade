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

"""Tests for Node class and NodeState enum."""

import pytest

from cascade.core.node import Node
from cascade.core.state import NodeState


class TestNodeState:
    """Tests for NodeState enum."""

    def test_state_names(self):
        """Test state names are correct."""
        assert NodeState.READY.name == "READY"
        assert NodeState.PENDING.name == "PENDING"
        assert NodeState.ACTIVE.name == "ACTIVE"
        assert NodeState.COMPLETED.name == "COMPLETED"
        assert NodeState.CANCELLED.name == "CANCELLED"
        assert NodeState.FAILED.name == "FAILED"

    def test_is_terminal(self):
        """Test is_terminal method."""
        assert NodeState.COMPLETED.is_terminal()
        assert NodeState.CANCELLED.is_terminal()
        assert NodeState.FAILED.is_terminal()
        assert not NodeState.READY.is_terminal()
        assert not NodeState.PENDING.is_terminal()
        assert not NodeState.ACTIVE.is_terminal()

    def test_is_executable(self):
        """Test is_executable method."""
        assert NodeState.READY.is_executable()
        assert not NodeState.PENDING.is_executable()
        assert not NodeState.ACTIVE.is_executable()

    def test_can_transition_to(self):
        """Test state transitions."""
        # READY -> ACTIVE
        assert NodeState.READY.can_transition_to(NodeState.ACTIVE)

        # PENDING -> READY
        assert NodeState.PENDING.can_transition_to(NodeState.READY)

        # ACTIVE -> COMPLETED/FAILED
        assert NodeState.ACTIVE.can_transition_to(NodeState.COMPLETED)
        assert NodeState.ACTIVE.can_transition_to(NodeState.FAILED)

        # Any -> CANCELLED
        assert NodeState.READY.can_transition_to(NodeState.CANCELLED)
        assert NodeState.ACTIVE.can_transition_to(NodeState.CANCELLED)

        # Invalid transitions
        assert not NodeState.COMPLETED.can_transition_to(NodeState.ACTIVE)
        assert not NodeState.FAILED.can_transition_to(NodeState.READY)


class TestNode:
    """Tests for Node class."""

    def test_node_creation(self):
        """Test creating a node."""
        node = Node(id="test", state=NodeState.READY)
        assert node.id == "test"
        assert node.state == NodeState.READY
        assert node.in_degree == 0
        assert node.context is None
        assert node.agent_id is None

    def test_node_with_agent_id(self):
        """Test creating a node with agent_id."""
        node = Node(id="test", agent_id="agent-001")
        assert node.agent_id == "agent-001"

    def test_update_state_valid(self):
        """Test valid state update."""
        node = Node(id="test", state=NodeState.READY)
        node.update_state(NodeState.ACTIVE)

        assert node.state == NodeState.ACTIVE

    def test_update_state_invalid(self):
        """Test invalid state update raises error."""
        node = Node(id="test", state=NodeState.COMPLETED)

        with pytest.raises(ValueError, match="Invalid state transition"):
            node.update_state(NodeState.ACTIVE)

    def test_decrement_in_degree(self):
        """Test decrementing in_degree."""
        node = Node(id="test", state=NodeState.PENDING, in_degree=2)
        node.decrement_in_degree()

        assert node.in_degree == 1

    def test_decrement_to_zero_becomes_ready(self):
        """Test decrementing to zero makes node ready."""
        node = Node(id="test", state=NodeState.PENDING, in_degree=1)
        node.decrement_in_degree()

        assert node.in_degree == 0
        assert node.state == NodeState.READY

    def test_increment_in_degree(self):
        """Test incrementing in_degree."""
        node = Node(id="test", state=NodeState.READY)
        node.increment_in_degree()

        assert node.in_degree == 1
        assert node.state == NodeState.PENDING

    def test_method_chaining(self):
        """Test methods return self for chaining."""
        node = (
            Node(id="test", state=NodeState.READY)
            .increment_in_degree()
            .increment_in_degree()
            .increment_in_degree()
        )

        assert node.in_degree == 3

    def test_repr(self):
        """Test string representation."""
        node = Node(id="test", state=NodeState.READY, in_degree=0)
        repr_str = repr(node)

        assert "test" in repr_str
        assert "READY" in repr_str
        assert "in_degree=0" in repr_str
