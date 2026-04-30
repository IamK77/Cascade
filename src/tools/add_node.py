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

"""Add Node Tool — thin wrapper delegating to CascadeClient."""

from typing import Any

from cascade.client import CascadeClient
from cascade.storage.protocol import StorageProtocol
from cascade.types import Contract


def add_node(storage: StorageProtocol, params: dict[str, Any]) -> dict[str, Any]:
    """Add a new node to the Cascade.

    Args:
        storage: StorageProtocol instance
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

    # Build expectations map and validate
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

    # Convert to dict[str, Contract] for CascadeClient
    deps: dict[str, Contract] | None = None
    if dependencies:
        deps = {
            dep_id: Contract(
                expectation=expectations_map[dep_id]["expectation"],
                promise=expectations_map[dep_id]["promise"],
            )
            for dep_id in dependencies
        }

    deps_dependents: dict[str, Contract] | None = None
    if dependents:
        deps_dependents = {
            dep_id: Contract(
                expectation=expectations_map[dep_id]["expectation"],
                promise=expectations_map[dep_id]["promise"],
            )
            for dep_id in dependents
        }

    client = CascadeClient(storage)

    r = client.add(node_id, deps=deps, dependents=deps_dependents)
    return r.to_dict()
