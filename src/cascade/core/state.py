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

"""Node state enumeration with transition rules encoded as data."""

from enum import Enum, auto


class NodeState(Enum):
    """Node state in the DAG.

    States represent the lifecycle of a node in the task graph:
    - READY: All dependencies met, can be executed
    - PENDING: Has unmet dependencies, must wait
    - ACTIVE: Currently being executed by an agent
    - COMPLETED: Finished successfully
    - CANCELLED: Cancelled (possibly cascaded from upstream)
    - FAILED: Execution failed
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
        return self in _TERMINAL_STATES

    def is_executable(self) -> bool:
        """Check if node can be claimed by an agent in this state."""
        return self == NodeState.READY

    def is_running(self) -> bool:
        """Check if node is currently being executed."""
        return self == NodeState.ACTIVE

    def can_transition_to(self, new_state: "NodeState") -> bool:
        """Check if transition to new_state is valid.

        Transition rules are encoded in _VALID_TRANSITIONS — this method
        is just a lookup, not a place to add ad-hoc logic.
        """
        if new_state == self:
            return True
        return new_state in _VALID_TRANSITIONS.get(self, frozenset())

    def __repr__(self) -> str:
        return f"NodeState.{self.name}"


# ---------------------------------------------------------------------------
# Transition rules — the single source of truth.
#
# Valid transitions:
#   READY   -> ACTIVE, FAILED, CANCELLED
#   PENDING -> READY, FAILED, CANCELLED
#   ACTIVE  -> COMPLETED, FAILED, CANCELLED, READY (release)
#   terminal states -> nothing (except self-transition, handled above)
#
# Notes:
# - ACTIVE -> READY represents "release" (agent gives up task).
# - PENDING/READY -> FAILED represents cascade failure (upstream dependency
#   failed, so this task can never proceed).
# ---------------------------------------------------------------------------
_VALID_TRANSITIONS: dict[NodeState, frozenset[NodeState]] = {
    NodeState.READY: frozenset({NodeState.ACTIVE, NodeState.FAILED, NodeState.CANCELLED}),
    NodeState.PENDING: frozenset({NodeState.READY, NodeState.FAILED, NodeState.CANCELLED}),
    NodeState.ACTIVE: frozenset({NodeState.COMPLETED, NodeState.FAILED, NodeState.CANCELLED, NodeState.READY}),
    NodeState.COMPLETED: frozenset({NodeState.CANCELLED}),
    NodeState.FAILED: frozenset({NodeState.CANCELLED}),
    NodeState.CANCELLED: frozenset(),
}

_TERMINAL_STATES: frozenset[NodeState] = frozenset({
    NodeState.COMPLETED,
    NodeState.CANCELLED,
    NodeState.FAILED,
})
