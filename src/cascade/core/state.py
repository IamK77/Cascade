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

"""Node state enumeration."""

from enum import Enum, auto


class NodeState(Enum):
    """Node state in the DAG.

    States represent the lifecycle of a node in the task graph:
    - READY: Node has no unmet dependencies and can be executed
    - PENDING: Node has unmet dependencies and must wait
    - ACTIVE: Node is currently being executed
    - COMPLETED: Node has finished successfully
    - CANCELLED: Node was cancelled (possibly due to cascade)
    - FAILED: Node execution failed
    """

    READY = auto()
    PENDING = auto()
    ACTIVE = auto()
    COMPLETED = auto()
    CANCELLED = auto()
    FAILED = auto()

    def __str__(self) -> str:
        return self.name

    def is_terminal(self) -> bool:
        """Check if this is a terminal state (no further transitions possible)."""
        return self in (NodeState.COMPLETED, NodeState.CANCELLED, NodeState.FAILED)

    def is_executable(self) -> bool:
        """Check if node can be executed in this state."""
        return self == NodeState.READY

    def is_running(self) -> bool:
        """Check if node is currently running."""
        return self == NodeState.ACTIVE

    def is_finished(self) -> bool:
        """Check if node has finished (successfully or not)."""
        return self.is_terminal() and self != NodeState.READY

    def can_transition_to(self, new_state: "NodeState") -> bool:
        """Check if transition to new_state is valid.

        Valid transitions:
        - READY -> ACTIVE
        - PENDING -> READY (when dependencies are met)
        - ACTIVE -> COMPLETED
        - ACTIVE -> FAILED
        - Any -> CANCELLED
        """
        if new_state == self:
            return True

        if self == NodeState.READY and new_state == NodeState.ACTIVE:
            return True
        if self == NodeState.PENDING and new_state == NodeState.READY:
            return True
        if self == NodeState.ACTIVE and new_state in (
            NodeState.COMPLETED,
            NodeState.FAILED,
        ):
            return True
        if new_state == NodeState.CANCELLED:
            return True
        return False

    def __repr__(self) -> str:
        return f"NodeState.{self.name}"
