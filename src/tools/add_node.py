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

"""Add Node Tool."""

from typing import Any

from cascade.core.cascade import Cascade
from cascade.core.node import Node
from cascade.core.state import NodeState
from cascade.storage.graph_storage import GraphStorage


def add_node(storage: GraphStorage, params: dict[str, Any]) -> dict[str, Any]:
    """Add a new node to the Cascade.

    Args:
        storage: GraphStorage instance
        params: Dictionary containing:
            - node_id (str, required): Unique identifier
            - dependencies (list[str], optional): Node IDs this node depends on
            - dependents (list[str], optional): Node IDs that depend on this node
            - expectations (list[dict], required if deps exist):
              List of {node_id, expectation, promise}

    Returns:
        Dict with success, message, data.
    """
    if "node_id" not in params:
        return {"success": False, "message": "Missing required parameter: node_id", "data": {}}

    node_id = params["node_id"]
    dependencies = params.get("dependencies", [])
    dependents = params.get("dependents", [])
    expectations = params.get("expectations", [])

    # Build expectations map
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
            expectations_map[exp_node_id] = {"expectation": expectation, "promise": promise}

    # Validate contracts exist for all edges
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

            if node_id in cascade.nodes:
                return {"success": False, "message": f"Node {node_id} already exists", "data": {}}

            for dep_id in dependencies:
                if dep_id not in cascade.nodes:
                    return {"success": False, "message": f"Dependency {dep_id} not found. Create it first.", "data": {}}
            for dep_id in dependents:
                if dep_id not in cascade.nodes:
                    return {"success": False, "message": f"Dependent {dep_id} not found. Create it first.", "data": {}}

            # Compute initial state: READY if no deps or all deps completed, else PENDING
            initial_state = NodeState.READY
            for dep_id in dependencies:
                if dep_id in cascade.nodes and cascade.nodes[dep_id].state != NodeState.COMPLETED:
                    initial_state = NodeState.PENDING
                    break

            node = Node(id=node_id, state=initial_state)
            cascade.add_node(node)
            affected_nodes = [node_id]

            for dep_id in dependencies:
                exp_info = expectations_map[dep_id]
                cascade.add_edge(dep_id, node_id, expectation=exp_info["expectation"], promise=exp_info["promise"])
                affected_nodes.append(dep_id)

            for dep_id in dependents:
                exp_info = expectations_map[dep_id]
                cascade.add_edge(node_id, dep_id, expectation=exp_info["expectation"], promise=exp_info["promise"])
                affected_nodes.append(dep_id)

            storage.save(cascade)
            from cascade.events import EventType
            storage.events.emit(EventType.NODE_ADDED, node_id=node_id,
                                dependencies=dependencies, dependents=dependents)
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
        return {"success": False, "message": f"Operation failed: {e}", "data": {}}
