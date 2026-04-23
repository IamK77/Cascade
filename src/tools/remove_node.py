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

"""Remove Node Tool."""

from typing import Any

from cascade.core.state import NodeState
from cascade.operations.remove import RemoveOperation
from cascade.storage.graph_storage import GraphStorage


def remove_node(storage: GraphStorage, params: dict[str, Any]) -> dict[str, Any]:
    """Remove a node from the DAG.

    Args:
        storage: GraphStorage instance
        params: Dictionary containing:
            - node_id (str, required)
            - cascade (bool, optional): Also remove dependents (default: False)
    """
    if "node_id" not in params:
        return {"success": False, "message": "Missing required parameter: node_id", "data": {}}

    node_id = params["node_id"]
    should_cascade = params.get("cascade", False)

    try:
        with storage.lock():
            from cascade.core.cascade import Cascade
            cascade = storage.load() or Cascade()

            if node_id not in cascade.nodes:
                return {"success": False, "message": f"Node {node_id} not found", "data": {}}

            node = cascade.nodes[node_id]
            if node.state == NodeState.ACTIVE:
                return {
                    "success": False,
                    "message": f"Cannot remove ACTIVE node {node_id} (agent: {node.agent_id}). "
                               f"Use finish_task with release=true first.",
                    "data": {"state": "ACTIVE", "agent_id": node.agent_id},
                }

            if should_cascade:
                active_descendants = [
                    dep.id for dep in cascade.get_dependents(node_id)
                    if dep.state == NodeState.ACTIVE
                ]
                if active_descendants:
                    return {
                        "success": False,
                        "message": f"Cannot cascade-remove: {active_descendants} are ACTIVE. "
                                   f"Release them first.",
                        "data": {"active_nodes": active_descendants},
                    }

            operation = RemoveOperation(cascade)
            result = operation.execute(node_id=node_id, cascade=should_cascade)

            storage.save(cascade)
            if result.success:
                from cascade.events import EventType
                storage.events.emit(EventType.NODE_REMOVED, node_id=node_id,
                                    cascade=should_cascade,
                                    affected_nodes=result.affected_nodes,
                                    reason=params.get("reason", ""))
            return {
                "success": result.success,
                "message": result.message,
                "data": {
                    "node_id": result.data.node_id if result.data else None,
                    "cascade": result.data.cascade if result.data else False,
                    "affected_nodes": result.affected_nodes,
                },
            }

    except Exception as e:
        return {"success": False, "message": f"Operation failed: {e}", "data": {}}
