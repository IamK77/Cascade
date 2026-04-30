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
from cascade.errors import InvalidTransitionError


class TestNodeState:
    """Tests for NodeState enum."""

    def test_state_names(self):
        assert NodeState.READY.name == "READY"
        assert NodeState.PENDING.name == "PENDING"
        assert NodeState.ACTIVE.name == "ACTIVE"
        assert NodeState.COMPLETED.name == "COMPLETED"
        assert NodeState.CANCELLED.name == "CANCELLED"
        assert NodeState.FAILED.name == "FAILED"

    def test_is_terminal(self):
        assert NodeState.COMPLETED.is_terminal()
        assert NodeState.CANCELLED.is_terminal()
        assert NodeState.FAILED.is_terminal()
        assert not NodeState.READY.is_terminal()
        assert not NodeState.PENDING.is_terminal()
        assert not NodeState.ACTIVE.is_terminal()

    def test_is_executable(self):
        assert NodeState.READY.is_executable()
        assert not NodeState.PENDING.is_executable()
        assert not NodeState.ACTIVE.is_executable()

    def test_can_transition_to(self):
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
        node = Node(id="test", state=NodeState.READY)
        assert node.id == "test"
        assert node.state == NodeState.READY
        assert node.context is None
        assert node.agent_id is None

    def test_node_with_agent_id(self):
        node = Node(id="test", agent_id="agent-001")
        assert node.agent_id == "agent-001"

    def test_update_state_valid(self):
        node = Node(id="test", state=NodeState.READY)
        node.update_state(NodeState.ACTIVE)
        assert node.state == NodeState.ACTIVE

    def test_update_state_invalid(self):
        node = Node(id="test", state=NodeState.COMPLETED)
        with pytest.raises(InvalidTransitionError, match="Invalid state transition"):
            node.update_state(NodeState.ACTIVE)

    def test_update_state_chaining(self):
        node = Node(id="test", state=NodeState.READY)
        result = node.update_state(NodeState.ACTIVE)
        assert result is node

    def test_repr(self):
        node = Node(id="test", state=NodeState.READY)
        repr_str = repr(node)
        assert "test" in repr_str
        assert "READY" in repr_str
