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

"""Refine Node Tool."""

from typing import Any

from cascade.storage.graph_storage import GraphStorage


def refine_node(storage: GraphStorage, params: dict[str, Any]) -> dict[str, Any]:
    """Add a new dependency to an existing node.

    Args:
        storage: GraphStorage instance
        params: Dictionary containing:
            - node_id (str, required)
            - dependency_id (str, required)
            - expectation (str, required)
            - promise (str, required)
    """
    if "node_id" not in params:
        return {"success": False, "message": "Missing required parameter: node_id", "data": {}}
    if "dependency_id" not in params:
        return {"success": False, "message": "Missing required parameter: dependency_id", "data": {}}

    node_id = params["node_id"]
    dependency_id = params["dependency_id"]
    expectation = params.get("expectation")
    promise = params.get("promise")

    if not expectation or not expectation.strip():
        return {"success": False, "message": "Missing required parameter: expectation", "data": {}}
    if not promise or not promise.strip():
        return {"success": False, "message": "Missing required parameter: promise", "data": {}}

    try:
        with storage.lock():
            from cascade.core.cascade import Cascade
            cascade = storage.load() or Cascade()

            if node_id not in cascade.nodes:
                return {"success": False, "message": f"Node {node_id} not found", "data": {}}
            if dependency_id not in cascade.nodes:
                return {"success": False, "message": f"Dependency {dependency_id} not found. Create it first with add_node.", "data": {}}

            if cascade.has_dependency(node_id, dependency_id):
                return {"success": False, "message": f"Node {node_id} already depends on {dependency_id}", "data": {}}

            if cascade._has_path(node_id, dependency_id):
                return {
                    "success": False,
                    "message": f"Adding dependency {dependency_id} to {node_id} would create a cycle",
                    "data": {},
                }

            cascade.add_edge(dependency_id, node_id, expectation=expectation, promise=promise)

            storage.save(cascade)
            from cascade.events import EventType
            storage.events.emit(EventType.NODE_REFINED, node_id=node_id,
                                dependency_id=dependency_id,
                                expectation=expectation, promise=promise,
                                reason=params.get("reason", ""))
            return {
                "success": True,
                "message": f"Node {node_id} now depends on {dependency_id}",
                "data": {"node_id": node_id, "dependency_id": dependency_id, "affected_nodes": [node_id, dependency_id]},
            }

    except Exception as e:
        return {"success": False, "message": f"Operation failed: {e}", "data": {}}
