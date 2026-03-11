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

"""Add node operation."""

from typing import Any

from cascade.operations.base import NodeOperation, OperationResult
from cascade.protocols.node_protocol import NodeProtocol


class AddOperation(NodeOperation):
    """Operation to add a new node to the DAG."""

    def execute(
        self,
        node: NodeProtocol,
        dependencies: list[str] | None = None,
        dependents: list[str] | None = None,
        contracts: dict[str, dict[str, str]] | None = None,
    ) -> OperationResult:
        """Add a node with optional dependency relationships.

        Args:
            node: Node to add
            dependencies: List of node IDs this node depends on
            dependents: List of node IDs that depend on this node
            contracts: Dict mapping node_id -> {expectation, promise} for each edge

        Returns:
            OperationResult with outcome
        """
        dependencies = dependencies or []
        dependents = dependents or []
        contracts = contracts or {}
        affected_nodes = [node.id]

        if node.id in self._cascade.nodes:
            return OperationResult(
                success=False,
                affected_nodes=[],
                message=f"Node {node.id} already exists",
            )

        valid, error = self._validate_nodes_exist(dependencies)
        if not valid:
            # Fail-fast: error must exist when validation fails
            assert error is not None, "Validation failed but no error message provided"
            return OperationResult(
                success=False,
                affected_nodes=[],
                message=error,
            )

        valid, error = self._validate_nodes_exist(dependents)
        if not valid:
            # Fail-fast: error must exist when validation fails
            assert error is not None, "Validation failed but no error message provided"
            return OperationResult(
                success=False,
                affected_nodes=[],
                message=error,
            )

        # Validate contracts for all edges
        all_edge_nodes = set(dependencies) | set(dependents)
        for edge_node_id in all_edge_nodes:
            if edge_node_id not in contracts:
                return OperationResult(
                    success=False,
                    affected_nodes=[],
                    message=f"Missing contract for '{edge_node_id}'",
                )
            contract = contracts[edge_node_id]
            if not contract.get("expectation") or not contract.get("promise"):
                return OperationResult(
                    success=False,
                    affected_nodes=[],
                    message=f"Contract for '{edge_node_id}' must have expectation and promise",
                )

        try:
            self._cascade.add_node(node)
            affected_nodes.append(node.id)

            for dep_id in dependencies:
                contract = contracts[dep_id]
                self._cascade.add_edge(
                    dep_id, node.id,
                    expectation=contract["expectation"],
                    promise=contract["promise"],
                )
                affected_nodes.append(dep_id)

            for dep_id in dependents:
                contract = contracts[dep_id]
                self._cascade.add_edge(
                    node.id, dep_id,
                    expectation=contract["expectation"],
                    promise=contract["promise"],
                )
                affected_nodes.append(dep_id)

            return OperationResult(
                success=True,
                affected_nodes=list(set(affected_nodes)),
                message=f"Node {node.id} added successfully",
                data={"node_id": node.id},
            )

        except ValueError as e:
            return OperationResult(
                success=False,
                affected_nodes=[],
                message=f"Failed to add node: {e}",
            )
