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

"""Remove node operation."""

from dataclasses import dataclass

from cascade.operations.base import NodeOperation, OperationResult


@dataclass(frozen=True)
class RemoveResult:
    """Typed payload for RemoveOperation success."""

    node_id: str
    cascade: bool


class RemoveOperation(NodeOperation):
    """Operation to remove a node from the DAG."""

    def execute(self, node_id: str, cascade: bool = False) -> OperationResult[RemoveResult]:
        valid, error = self._validate_node_exists(node_id)
        if not valid:
            assert error is not None
            return OperationResult(success=False, affected_nodes=[], message=error)

        affected_nodes: set[str] = set()

        if cascade:
            to_remove = self._collect_descendants(node_id)
            for nid in to_remove:
                for dep in self._cascade.get_dependents(nid):
                    affected_nodes.add(dep.id)
                for dep in self._cascade.get_dependencies(nid):
                    affected_nodes.add(dep.id)
                self._cascade.remove_node(nid)
                affected_nodes.add(nid)
        else:
            for dep in self._cascade.get_dependents(node_id):
                affected_nodes.add(dep.id)
            for dep in self._cascade.get_dependencies(node_id):
                affected_nodes.add(dep.id)
            self._cascade.remove_node(node_id)
            affected_nodes.add(node_id)

        return OperationResult(
            success=True,
            affected_nodes=list(affected_nodes),
            message=f"Node {node_id} removed successfully",
            data=RemoveResult(node_id=node_id, cascade=cascade),
        )

    def _collect_descendants(self, node_id: str) -> set[str]:
        descendants: set[str] = {node_id}
        queue = [node_id]
        visited = {node_id}

        while queue:
            current = queue.pop(0)
            for dependent in self._cascade.get_dependents(current):
                if dependent.id not in visited:
                    visited.add(dependent.id)
                    descendants.add(dependent.id)
                    queue.append(dependent.id)

        return descendants

    def remove(self, node_id: str, cascade: bool = False) -> OperationResult[RemoveResult]:
        return self.execute(node_id, cascade)
