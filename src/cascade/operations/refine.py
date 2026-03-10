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

"""Refine node operation."""

from collections.abc import Sequence

from cascade.operations.base import NodeOperation, OperationResult
from cascade.protocols.node_protocol import NodeProtocol


class RefineOperation(NodeOperation):
    """Operation to refine a node by adding new dependencies.

    Unlike split, this keeps the original node and adds new nodes
    that the original node depends on. This is useful when a node
    discovers missing dependencies during execution.
    """

    def execute(self, node_id: str, new_dependencies: Sequence[NodeProtocol]) -> OperationResult:
        """Refine a node by adding new dependency nodes.

        Args:
            node_id: ID of the node to refine (target node)
            new_dependencies: List of new nodes to add as dependencies

        Returns:
            OperationResult with outcome
        """
        valid, error = self._validate_node_exists(node_id)
        if not valid:
            # Fail-fast: error must exist when validation fails
            assert error is not None, "Validation failed but no error message provided"
            return OperationResult(
                success=False,
                affected_nodes=[],
                message=error,
            )

        original_dependencies = self._cascade.get_dependencies(node_id)
        affected_nodes = [node_id]
        new_node_ids = []

        for node in new_dependencies:
            if node.id in self._cascade.nodes:
                return OperationResult(
                    success=False,
                    affected_nodes=[],
                    message=f"Node {node.id} already exists",
                )
            new_node_ids.append(node.id)

        try:
            for node in new_dependencies:
                self._cascade.add_node(node)
                new_node_ids.append(node.id)
                affected_nodes.append(node.id)

                self._cascade.add_edge(node.id, node_id)

                # New nodes inherit target's original dependencies
                for dep in original_dependencies:
                    self._cascade.add_edge(dep.id, node.id)
                    affected_nodes.append(dep.id)

            return OperationResult(
                success=True,
                affected_nodes=list(set(affected_nodes)),
                message=f"Node {node_id} refined with {len(new_dependencies)} new dependencies",
                data={
                    "target_id": node_id,
                    "new_dependency_ids": new_node_ids,
                },
            )

        except ValueError as e:
            return OperationResult(
                success=False,
                affected_nodes=[],
                message=f"Failed to refine node: {e}",
            )

    def refine(self, node_id: str, new_dependencies: list[NodeProtocol]) -> OperationResult:
        """Convenience method for refine operation.

        Args:
            node_id: ID of the node to refine (target node)
            new_dependencies: List of new nodes to add as dependencies

        Returns:
            OperationResult with outcome
        """
        return self.execute(node_id, new_dependencies)
