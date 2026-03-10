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

"""Protocol interface definitions for nodes."""

from typing import Protocol, Self

from cascade.core.state import NodeState
from cascade.protocols.context_protocol import ContextProtocol


class NodeProtocol(Protocol):
    """Protocol interface for Cascade nodes.

    A node represents a task with:
    - Unique identifier
    - State tracking (READY, PENDING, ACTIVE, etc.)
    - in_degree: count of uncompleted dependencies
    - Optional context for information propagation
    - Optional agent assignment tracking

    Note: Contract information (expectation/promise) is stored on edges,
    not on nodes. Use cascade.get_edge_metadata(from_id, to_id) to query.
    """

    @property
    def id(self) -> str:
        """Unique node identifier."""
        ...

    @property
    def state(self) -> NodeState:
        """Current node state."""
        ...

    @state.setter
    def state(self, value: NodeState) -> None:
        """Set node state."""
        ...

    @property
    def in_degree(self) -> int:
        """Number of uncompleted dependencies."""
        ...

    @property
    def context(self) -> ContextProtocol | None:
        """Optional context for information propagation."""
        ...

    @context.setter
    def context(self, value: ContextProtocol | None) -> None:
        """Set node context."""
        ...

    @property
    def agent_id(self) -> str | None:
        """ID of agent currently working on this task."""
        ...

    @agent_id.setter
    def agent_id(self, value: str | None) -> None:
        """Set agent ID."""
        ...

    def update_state(self, new_state: NodeState) -> Self:
        """Update the node state.

        Args:
            new_state: New state to transition to

        Returns:
            Self for method chaining

        Raises:
            ValueError: If state transition is invalid
        """
        ...

    def decrement_in_degree(self) -> Self:
        """Decrement in-degree when a dependency completes.

        Returns:
            Self for method chaining
        """
        ...

    def increment_in_degree(self) -> Self:
        """Increment in-degree when a new dependency is added.

        Returns:
            Self for method chaining
        """
        ...
