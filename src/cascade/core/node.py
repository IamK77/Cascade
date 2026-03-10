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

"""Node implementation for DAG."""

from dataclasses import dataclass, field

from cascade.core.state import NodeState
from cascade.protocols.context_protocol import ContextProtocol


@dataclass
class Node:
    """Concrete implementation of a DAG node.

    A node represents a task with:
    - Unique identifier
    - Execution state
    - in_degree: count of uncompleted dependencies
    - Optional context for information propagation
    - Optional agent_id tracking which agent is working on this task

    Note: promise and expectation are stored on edges (edge_metadata),
    not on nodes. A node may have different promises to different downstream nodes.
    """

    id: str
    state: NodeState = NodeState.PENDING
    in_degree: int = 0
    context: ContextProtocol | None = None
    agent_id: str | None = None  # Agent currently working on this task

    def update_state(self, new_state: NodeState) -> "Node":
        """Update the node state.

        Args:
            new_state: New state to transition to

        Returns:
            Self for method chaining

        Raises:
            ValueError: If state transition is invalid
        """
        if not self.state.can_transition_to(new_state):
            raise ValueError(f"Invalid state transition: {self.state} -> {new_state}")
        self.state = new_state
        return self

    def decrement_in_degree(self) -> "Node":
        """Decrement in-degree when a dependency completes.

        Returns:
            Self for method chaining
        """
        self.in_degree = max(0, self.in_degree - 1)
        if self.in_degree == 0:
            self.state = NodeState.READY
        return self

    def increment_in_degree(self) -> "Node":
        """Increment in-degree when a new dependency is added.

        Returns:
            Self for method chaining
        """
        self.in_degree += 1
        if self.state == NodeState.READY:
            self.state = NodeState.PENDING
        return self

    def __repr__(self) -> str:
        return f"Node(id={self.id!r}, state={self.state}, in_degree={self.in_degree})"
