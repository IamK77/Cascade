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
from dataclasses import dataclass

from cascade.core.node import Node
from cascade.operations.base import NodeOperation, OperationResult
from cascade.types import Contract


@dataclass(frozen=True)
class SplitResult:
    """Typed payload for SplitOperation success."""

    parent_id: str
    new_node_ids: list[str]


class SplitOperation(NodeOperation):
    """Split a node into multiple replacement nodes.

    The original node is removed. Its dependencies and dependents are
    re-wired to the new nodes, preserving contracts.
    """

    def execute(self, parent_id: str, new_nodes: Sequence[Node]) -> OperationResult[SplitResult]:
        valid, error = self._validate_node_exists(parent_id)
        if not valid:
            assert error is not None
            return OperationResult(success=False, affected_nodes=[], message=error)

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
            # Collect contracts before removing parent
            incoming_contracts: dict[str, Contract] = {}
            for dep in dependencies:
                contract = self._cascade.get_contract(dep.id, parent_id)
                incoming_contracts[dep.id] = contract or Contract(
                    expectation=f"Output from {dep.id}",
                    promise=f"Input for split nodes from {dep.id}",
                )

            outgoing_contracts: dict[str, Contract] = {}
            for dep in dependents:
                contract = self._cascade.get_contract(parent_id, dep.id)
                outgoing_contracts[dep.id] = contract or Contract(
                    expectation="Output from split nodes",
                    promise=f"Input for {dep.id}",
                )

            self._cascade.remove_node(parent_id)

            for node in new_nodes:
                self._cascade.add_node(node)
                affected_nodes.append(node.id)

            for dep in dependencies:
                c = incoming_contracts[dep.id]
                for new_id in new_node_ids:
                    self._cascade.add_edge(dep.id, new_id, contract=c)
                    affected_nodes.append(dep.id)

            for dep in dependents:
                c = outgoing_contracts[dep.id]
                for new_id in new_node_ids:
                    self._cascade.add_edge(new_id, dep.id, contract=c)
                    affected_nodes.append(dep.id)

            return OperationResult(
                success=True,
                affected_nodes=list(set(affected_nodes)),
                message=f"Node {parent_id} split into {len(new_nodes)} nodes",
                data=SplitResult(parent_id=parent_id, new_node_ids=new_node_ids),
            )
        except ValueError as e:
            return OperationResult(
                success=False,
                affected_nodes=[],
                message=f"Failed to split node: {e}",
            )

    def split(self, parent_id: str, new_nodes: list[Node]) -> OperationResult[SplitResult]:
        return self.execute(parent_id, new_nodes)
