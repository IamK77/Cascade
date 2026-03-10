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

"""Base class for node operations."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from cascade.core.cascade import Cascade


@dataclass
class OperationResult:
    """Result of a node operation."""

    success: bool
    """Whether the operation succeeded."""

    affected_nodes: list[str]
    """List of node IDs affected by the operation."""

    message: str
    """Human-readable result message."""

    data: dict[str, Any]
    """Additional operation-specific data."""

    def __init__(
        self,
        success: bool,
        affected_nodes: list[str],
        message: str = "",
        data: dict[str, Any] | None = None,
    ):
        self.success = success
        self.affected_nodes = affected_nodes
        self.message = message
        self.data = data or {}

    def __repr__(self) -> str:
        status = "Success" if self.success else "Failed"
        return f"OperationResult({status}, nodes={len(self.affected_nodes)})"


class NodeOperation(ABC):
    """Base class for all node operations.

    Operations modify the Cascade structure by adding, removing, splitting,
    or refining nodes. All operations perform cycle detection.
    """

    def __init__(self, cascade: Cascade):
        """Create an operation for a Cascade.

        Args:
            cascade: The Cascade to operate on
        """
        self._cascade = cascade

    @abstractmethod
    def execute(self, *args: Any, **kwargs: Any) -> OperationResult:
        """Execute the operation.

        Returns:
            OperationResult with outcome details
        """
        ...

    def validate(self) -> tuple[bool, str | None]:
        """Validate the operation before execution.

        Returns:
            Tuple of (is_valid, error_message)
        """
        is_acyclic, error = self._cascade.find_cycle() is None, None
        if self._cascade.has_cycle():
            cycle_info = self._cascade.find_cycle()
            error = f"Graph contains cycle: {cycle_info}"
        return is_acyclic, error

    def _validate_node_exists(self, node_id: str) -> tuple[bool, str | None]:
        """Check if a node exists.

        Args:
            node_id: Node ID to check

        Returns:
            Tuple of (exists, error_message)
        """
        if node_id not in self._cascade.nodes:
            return False, f"Node {node_id} not found"
        return True, None

    def _validate_nodes_exist(self, node_ids: list[str]) -> tuple[bool, str | None]:
        """Check if multiple nodes exist.

        Args:
            node_ids: List of node IDs to check

        Returns:
            Tuple of (all_exist, error_message)
        """
        for node_id in node_ids:
            valid, error = self._validate_node_exists(node_id)
            if not valid:
                return False, error
        return True, None
