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
"""

from dataclasses import dataclass

from cascade.core.state import NodeState
from cascade.errors import InvalidTransitionError
from cascade.types import Context


@dataclass
class Node:
    """A task node in the DAG.

    Fields:
        id: Unique identifier.
        state: Current lifecycle state.
        context: Optional context for information propagation.
        agent_id: ID of the agent currently working on this task, if any.
        claimed_at: Timestamp (time.time()) when the task was claimed (ACTIVE).
                    Set when entering ACTIVE, cleared when leaving ACTIVE.
        timeout: Optional timeout in seconds. If set, the task is considered
                 stalled after claimed_at + timeout and can be auto-released.
    """

    id: str
    state: NodeState = NodeState.PENDING
    context: Context | None = None
    agent_id: str | None = None
    claimed_at: float | None = None
    timeout: float | None = None

    def update_state(self, new_state: NodeState) -> "Node":
        """Transition to a new state.

        Raises:
            ValueError: If the transition is invalid per NodeState rules.

        Returns:
            Self for method chaining.
        """
        if not self.state.can_transition_to(new_state):
            raise InvalidTransitionError(f"Invalid state transition: {self.state} -> {new_state}")
        self.state = new_state
        return self

    def is_timed_out(self, now: float) -> bool:
        """Check if this node has exceeded its timeout.

        Only meaningful for ACTIVE nodes with both claimed_at and timeout set.
        """
        if self.state != NodeState.ACTIVE:
            return False
        if self.claimed_at is None or self.timeout is None:
            return False
        return now - self.claimed_at >= self.timeout

    def __repr__(self) -> str:
        parts = [f"id={self.id!r}", f"state={self.state}"]
        if self.agent_id:
            parts.append(f"agent={self.agent_id!r}")
        return f"Node({', '.join(parts)})"
