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

"""Node implementation for DAG.

A Node is a pure data object — it knows its own identity, state, context,
and agent assignment, but nothing about the graph structure it lives in.

Notably, there is no `in_degree` field. Dependency count is a property of
the graph, not the node. It is computed by Cascade from the adjacency
structure and the states of upstream nodes.
"""

from dataclasses import dataclass

from cascade.context.context import Context
from cascade.core.state import NodeState


@dataclass
class Node:
    """A task node in the DAG.

    Fields:
        id: Unique identifier.
        state: Current lifecycle state.
        context: Optional context for information propagation.
        agent_id: ID of the agent currently working on this task, if any.
    """

    id: str
    state: NodeState = NodeState.PENDING
    context: Context | None = None
    agent_id: str | None = None

    def update_state(self, new_state: NodeState) -> "Node":
        """Transition to a new state.

        Raises:
            ValueError: If the transition is invalid per NodeState rules.

        Returns:
            Self for method chaining.
        """
        if not self.state.can_transition_to(new_state):
            raise ValueError(f"Invalid state transition: {self.state} -> {new_state}")
        self.state = new_state
        return self

    def __repr__(self) -> str:
        parts = [f"id={self.id!r}", f"state={self.state}"]
        if self.agent_id:
            parts.append(f"agent={self.agent_id!r}")
        return f"Node({', '.join(parts)})"
