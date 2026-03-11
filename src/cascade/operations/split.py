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

"""Split node operation."""

from collections.abc import Sequence

from cascade.operations.base import NodeOperation, OperationResult
from cascade.protocols.node_protocol import NodeProtocol


class SplitOperation(NodeOperation):
    """Operation to split a node into multiple nodes.

    The original node is removed and replaced with new nodes.
    Dependencies from the original node are transferred appropriately.
    """

    def execute(self, parent_id: str, new_nodes: Sequence[NodeProtocol]) -> OperationResult:
        """Split a node into multiple new nodes.

        Args:
            parent_id: ID of the node to split
            new_nodes: List of new nodes to replace the parent

        Returns:
            OperationResult with outcome
        """
        valid, error = self._validate_node_exists(parent_id)
        if not valid:
            # Fail-fast: error must exist when validation fails
            assert error is not None, "Validation failed but no error message provided"
            return OperationResult(
                success=False,
                affected_nodes=[],
                message=error,
            )

        dependents = self._cascade.get_dependents(parent_id)
        dependencies = self._cascade.get_dependencies(parent_id)
        affected_nodes = [parent_id]

        new_node_ids = []
        for node in new_nodes:
            if node.id in self._cascade.nodes and node.id != parent_id:
                return OperationResult(
                    success=False,
                    affected_nodes=[],
                    message=f"Node {node.id} already exists",
                )
            new_node_ids.append(node.id)

        try:
            # Collect edge metadata before removing parent
            incoming_contracts: dict[str, dict[str, str]] = {}
            for dependency in dependencies:
                metadata = self._cascade.get_edge_metadata(dependency.id, parent_id)
                incoming_contracts[dependency.id] = {
                    "expectation": metadata.get("expectation") or f"Output from {dependency.id}",
                    "promise": metadata.get("promise") or f"Input for split nodes from {dependency.id}",
                }

            outgoing_contracts: dict[str, dict[str, str]] = {}
            for dependent in dependents:
                metadata = self._cascade.get_edge_metadata(parent_id, dependent.id)
                outgoing_contracts[dependent.id] = {
                    "expectation": metadata.get("expectation") or f"Output from split nodes",
                    "promise": metadata.get("promise") or f"Input for {dependent.id}",
                }

            self._cascade.remove_node(parent_id)

            for node in new_nodes:
                self._cascade.add_node(node)
                affected_nodes.append(node.id)

            # New nodes inherit parent's dependencies with contracts
            for dependency in dependencies:
                contract = incoming_contracts[dependency.id]
                for new_id in new_node_ids:
                    self._cascade.add_edge(
                        dependency.id,
                        new_id,
                        expectation=contract["expectation"],
                        promise=contract["promise"],
                    )
                    affected_nodes.append(dependency.id)

            # Parent's dependents now depend on all new nodes with contracts
            for dependent in dependents:
                contract = outgoing_contracts[dependent.id]
                for new_id in new_node_ids:
                    self._cascade.add_edge(
                        new_id,
                        dependent.id,
                        expectation=contract["expectation"],
                        promise=contract["promise"],
                    )
                    affected_nodes.append(dependent.id)

            return OperationResult(
                success=True,
                affected_nodes=list(set(affected_nodes)),
                message=f"Node {parent_id} split into {len(new_nodes)} nodes",
                data={
                    "parent_id": parent_id,
                    "new_node_ids": new_node_ids,
                },
            )

        except ValueError as e:
            return OperationResult(
                success=False,
                affected_nodes=[],
                message=f"Failed to split node: {e}",
            )

    def split(self, parent_id: str, new_nodes: list[NodeProtocol]) -> OperationResult:
        """Convenience method for split operation.

        Args:
            parent_id: ID of the node to split
            new_nodes: List of new nodes to replace the parent

        Returns:
            OperationResult with outcome
        """
        return self.execute(parent_id, new_nodes)
