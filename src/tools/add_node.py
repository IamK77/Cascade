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

"""Add Node Tool.

Add a new node to the DAG with optional dependency relationships.
This is the primary way to create new tasks in the task graph.

The initial state is automatically computed:
- No dependencies: READY (can be executed immediately)
- Has dependencies: PENDING (waiting for dependencies to complete)
"""

from typing import Any

from cascade.core.cascade import Cascade
from cascade.core.node import Node
from cascade.core.state import NodeState
from cascade.storage.graph_storage import GraphStorage


def _compute_initial_state(cascade: Cascade, dependencies: list[str]) -> NodeState:
    """Compute the initial state for a new node."""
    if not dependencies:
        return NodeState.READY

    for dep_id in dependencies:
        if dep_id not in cascade.nodes:
            return NodeState.PENDING
        dep_node = cascade.nodes[dep_id]
        if dep_node.state != NodeState.COMPLETED:
            return NodeState.PENDING

    return NodeState.READY


def add_node(storage: GraphStorage, params: dict[str, Any]) -> dict[str, Any]:
    """Add a new node to the Cascade.

    Automatically handles locking, loading, saving.

    Args:
        storage: GraphStorage instance
        params: Dictionary containing:
            - node_id (str, required): Unique identifier for the node
            - dependencies (List[str], optional): List of node IDs this node depends on
            - dependents (List[str], optional): List of node IDs that depend on this node
            - expectations (List[Dict], required if dependencies/dependents exist):
              List of {node_id, expectation, promise} for each dependency/dependent edge

    Returns:
        Dict with:
            - success (bool): Whether the operation succeeded
            - message (str): Human-readable result message
            - data (dict): Contains "node_id", "state", and "affected_nodes"
    """
    if "node_id" not in params:
        return {
            "success": False,
            "message": "Missing required parameter: node_id",
            "data": {},
        }

    node_id = params["node_id"]
    dependencies = params.get("dependencies", [])
    dependents = params.get("dependents", [])
    expectations = params.get("expectations", [])

    # Build expectations map for validation and lookup
    expectations_map: dict[str, dict[str, str]] = {}
    for exp in expectations:
        exp_node_id = exp.get("node_id")
        expectation = exp.get("expectation")
        promise = exp.get("promise")
        if exp_node_id:
            if not expectation or not expectation.strip():
                return {
                    "success": False,
                    "message": f"expectation is required for node '{exp_node_id}' in expectations",
                    "data": {},
                }
            if not promise or not promise.strip():
                return {
                    "success": False,
                    "message": f"promise is required for node '{exp_node_id}' in expectations",
                    "data": {},
                }
            expectations_map[exp_node_id] = {
                "expectation": expectation,
                "promise": promise,
            }

    # Validate that all dependencies have corresponding expectations
    for dep_id in dependencies:
        if dep_id not in expectations_map:
            return {
                "success": False,
                "message": (
                    f"Missing contract for dependency '{dep_id}'. "
                    f"Each dependency must have expectation and promise in 'expectations' parameter."
                ),
                "data": {"missing_contract_for": dep_id},
            }

    # Validate that all dependents have corresponding expectations
    for dep_id in dependents:
        if dep_id not in expectations_map:
            return {
                "success": False,
                "message": (
                    f"Missing contract for dependent '{dep_id}'. "
                    f"Each dependent must have expectation and promise in 'expectations' parameter."
                ),
                "data": {"missing_contract_for": dep_id},
            }

    try:
        with storage.lock():
            cascade = storage.load() or Cascade()

            # Check if node already exists
            if node_id in cascade.nodes:
                return {
                    "success": False,
                    "message": f"Node {node_id} already exists",
                    "data": {},
                }

            # Enforce no isolated nodes:
            # - Empty graph: allow one root node (no dependencies/dependents)
            # - Non-empty graph: new node MUST have dependencies OR dependents
            if cascade.nodes and not dependencies and not dependents:
                return {
                    "success": False,
                    "message": (
                        f"Isolated nodes not allowed. "
                        f"Node '{node_id}' must specify 'dependencies' (depend on existing nodes) "
                        f"or 'dependents' (existing nodes that will depend on this node). "
                        f"Existing nodes: {list(cascade.nodes.keys())}"
                    ),
                    "data": {"existing_nodes": list(cascade.nodes.keys())},
                }

            # Validate dependencies exist
            for dep_id in dependencies:
                if dep_id not in cascade.nodes:
                    return {
                        "success": False,
                        "message": f"Dependency {dep_id} not found. Create it first.",
                        "data": {},
                    }

            # Validate dependents exist
            for dep_id in dependents:
                if dep_id not in cascade.nodes:
                    return {
                        "success": False,
                        "message": f"Dependent {dep_id} not found. Create it first.",
                        "data": {},
                    }

            # Compute initial state automatically
            initial_state = _compute_initial_state(cascade, dependencies)

            # Create and add node
            node = Node(id=node_id, state=initial_state)
            cascade.add_node(node)

            affected_nodes = [node_id]

            # Add edges for dependencies (dep_id -> node_id means node depends on dep)
            for dep_id in dependencies:
                exp_info = expectations_map[dep_id]
                cascade.add_edge(
                    dep_id,
                    node_id,
                    expectation=exp_info["expectation"],
                    promise=exp_info["promise"],
                )
                affected_nodes.append(dep_id)

            # Add edges for dependents (node_id -> dep_id means dep depends on node)
            for dep_id in dependents:
                exp_info = expectations_map[dep_id]
                cascade.add_edge(
                    node_id,
                    dep_id,
                    expectation=exp_info["expectation"],
                    promise=exp_info["promise"],
                )
                affected_nodes.append(dep_id)

            # Verify graph is still a single connected DAG
            if not cascade.is_connected():
                # Rollback: remove the node we just added
                cascade.remove_node(node_id)
                return {
                    "success": False,
                    "message": (
                        f"Adding node '{node_id}' would create disconnected subgraphs. "
                        f"All nodes must belong to a single connected DAG. "
                        f"Connect to existing nodes: {list(cascade.nodes.keys())}"
                    ),
                    "data": {"existing_nodes": list(cascade.nodes.keys())},
                }

            storage.save(cascade)

            return {
                "success": True,
                "message": f"Node {node_id} added successfully",
                "data": {
                    "node_id": node_id,
                    "state": initial_state.name,
                    "affected_nodes": list(set(affected_nodes)),
                },
            }

    except Exception as e:
        return {
            "success": False,
            "message": f"Operation failed: {e}",
            "data": {},
        }
