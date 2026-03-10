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

"""Refine Node Tool.

Add a new dependency to an existing node.
Use this when you discover that a task has a prerequisite that wasn't planned.
The node will wait for the new dependency to complete before becoming ready.
"""

from typing import Any

from cascade.core.state import NodeState
from cascade.storage.graph_storage import GraphStorage


def refine_node(storage: GraphStorage, params: dict[str, Any]) -> dict[str, Any]:
    """Add a new dependency to an existing node.

    Automatically handles locking, loading, saving.

    This increases the node's in-degree and changes its state from READY to PENDING
    if it was previously READY. The node will not become executable until the new
    dependency also completes.

    Args:
        storage: GraphStorage instance
        params: Dictionary containing:
            - node_id (str, required): ID of the node to add a dependency to
            - dependency_id (str, required): ID of the new dependency node
            - expectation (str, optional): What node_id expects from dependency_id
            - promise (str, optional): What dependency_id promises to output

    Returns:
        Dict with:
            - success (bool): Whether the operation succeeded
            - message (str): Human-readable result message
            - data (dict): Contains "node_id", "dependency_id", and "affected_nodes"
    """
    if "node_id" not in params:
        return {
            "success": False,
            "message": "Missing required parameter: node_id",
            "data": {},
        }

    if "dependency_id" not in params:
        return {
            "success": False,
            "message": "Missing required parameter: dependency_id",
            "data": {},
        }

    node_id = params["node_id"]
    dependency_id = params["dependency_id"]
    expectation = params.get("expectation")
    promise = params.get("promise")

    try:
        with storage.lock():
            from cascade.core.cascade import Cascade
            cascade = storage.load() or Cascade()

            if node_id not in cascade.nodes:
                return {
                    "success": False,
                    "message": f"Node {node_id} not found",
                    "data": {},
                }

            if dependency_id not in cascade.nodes:
                return {
                    "success": False,
                    "message": f"Dependency {dependency_id} not found. Create it first with add_node.",
                    "data": {},
                }

            # Check if edge already exists
            if dependency_id in cascade.reverse_adjacency.get(node_id, set()):
                return {
                    "success": False,
                    "message": f"Node {node_id} already depends on {dependency_id}",
                    "data": {},
                }

            # Check for cycle
            if cascade._has_path(node_id, dependency_id):
                return {
                    "success": False,
                    "message": f"Adding dependency {dependency_id} to {node_id} would create a cycle",
                    "data": {},
                }

            # Add edge with metadata (this handles in_degree automatically)
            cascade.add_edge(dependency_id, node_id, expectation=expectation, promise=promise)

            # Update node state if it was READY (now has unmet dependency)
            node = cascade.nodes[node_id]
            if node.state == NodeState.READY:
                node.state = NodeState.PENDING

            affected_nodes = [node_id, dependency_id]

            storage.save(cascade)

            return {
                "success": True,
                "message": f"Node {node_id} now depends on {dependency_id}",
                "data": {
                    "node_id": node_id,
                    "dependency_id": dependency_id,
                    "affected_nodes": affected_nodes,
                },
            }

    except Exception as e:
        return {
            "success": False,
            "message": f"Operation failed: {e}",
            "data": {},
        }
