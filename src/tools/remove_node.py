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

"""Remove Node Tool.

Remove a node from the DAG with optional cascading deletion of dependent nodes.
Use this when a task is no longer needed or was created in error.
"""

from typing import Any

from cascade.storage.graph_storage import GraphStorage
from cascade.operations.remove import RemoveOperation


def remove_node(storage: GraphStorage, params: dict[str, Any]) -> dict[str, Any]:
    """Remove a node from the DAG.

    Automatically handles locking, loading, saving.

    Args:
        storage: GraphStorage instance
        params: Dictionary containing:
            - node_id (str, required): ID of the node to remove
            - cascade (bool, optional): If True, also remove all dependent nodes (default: False)

    Returns:
        Dict with:
            - success (bool): Whether the operation succeeded
            - message (str): Human-readable result message
            - data (dict): Contains "node_id", "cascade", and "affected_nodes"
    """
    if "node_id" not in params:
        return {
            "success": False,
            "message": "Missing required parameter: node_id",
            "data": {},
        }

    node_id = params["node_id"]
    should_cascade = params.get("cascade", False)

    try:
        with storage.lock():
            from cascade.core.cascade import Cascade
            cascade = storage.load() or Cascade()

            operation = RemoveOperation(cascade)
            result = operation.execute(node_id=node_id, cascade=should_cascade)

            storage.save(cascade)

            return {
                "success": result.success,
                "message": result.message,
                "data": {
                    "node_id": result.data.get("node_id"),
                    "cascade": result.data.get("cascade"),
                    "affected_nodes": result.affected_nodes,
                },
            }

    except Exception as e:
        return {
            "success": False,
            "message": f"Operation failed: {e}",
            "data": {},
        }
