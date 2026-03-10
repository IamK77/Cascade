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

"""Split Node Tool.

Split an existing node into multiple nodes.
Use this when a task is too broad and needs to be broken down.
The original node is replaced by the new nodes.
"""

from typing import Any

from cascade.core.node import Node
from cascade.operations.split import SplitOperation
from cascade.storage.graph_storage import GraphStorage


def split_node(storage: GraphStorage, params: dict[str, Any]) -> dict[str, Any]:
    """Split a node into multiple new nodes.

    Automatically handles locking, loading, saving.

    The original node is removed and replaced with the new nodes.
    Dependencies from the original node are inherited by all new nodes.
    Dependents of the original node will now depend on all new nodes.

    Args:
        storage: GraphStorage instance
        params: Dictionary containing:
            - parent_id (str, required): ID of the node to split
            - new_nodes (List[Dict], required): List of new node definitions
              Each dict should have: node_id

    Returns:
        Dict with:
            - success (bool): Whether the operation succeeded
            - message (str): Human-readable result message
            - data (dict): Contains "parent_id", "new_node_ids", and "affected_nodes"
    """
    if "parent_id" not in params:
        return {
            "success": False,
            "message": "Missing required parameter: parent_id",
            "data": {},
        }

    if "new_nodes" not in params:
        return {
            "success": False,
            "message": "Missing required parameter: new_nodes",
            "data": {},
        }

    parent_id = params["parent_id"]
    new_nodes_data = params["new_nodes"]

    if not isinstance(new_nodes_data, list) or len(new_nodes_data) == 0:
        return {
            "success": False,
            "message": "new_nodes must be a non-empty list",
            "data": {},
        }

    try:
        with storage.lock():
            from cascade.core.cascade import Cascade
            cascade = storage.load() or Cascade()

            if parent_id not in cascade.nodes:
                return {
                    "success": False,
                    "message": f"Parent node {parent_id} not found",
                    "data": {},
                }

            parent_state = cascade.nodes[parent_id].state

            new_nodes = []
            for node_data in new_nodes_data:
                if "node_id" not in node_data:
                    return {
                        "success": False,
                        "message": "Each new node must have a node_id",
                        "data": {},
                    }

                node = Node(
                    id=node_data["node_id"],
                    state=parent_state,
                )
                new_nodes.append(node)

            operation = SplitOperation(cascade)
            result = operation.execute(parent_id=parent_id, new_nodes=new_nodes)

            storage.save(cascade)

            return {
                "success": result.success,
                "message": result.message,
                "data": {
                    "parent_id": result.data.get("parent_id"),
                    "new_node_ids": result.data.get("new_node_ids"),
                    "affected_nodes": result.affected_nodes,
                },
            }

    except Exception as e:
        return {
            "success": False,
            "message": f"Operation failed: {e}",
            "data": {},
        }
