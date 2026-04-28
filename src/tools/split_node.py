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

"""Split Node Tool — thin wrapper delegating to CascadeClient."""

from typing import Any

from cascade.client import CascadeClient
from cascade.storage.graph_storage import GraphStorage


def split_node(storage: GraphStorage, params: dict[str, Any]) -> dict[str, Any]:
    """Split a node into multiple new nodes.

    Args:
        storage: GraphStorage instance
        params: Dictionary containing:
            - parent_id (str, required)
            - new_nodes (list[dict], required): Each dict has node_id
            - reason (str, optional): Why
    """
    if "parent_id" not in params:
        return {"success": False, "message": "Missing required parameter: parent_id", "data": {}}
    if "new_nodes" not in params:
        return {"success": False, "message": "Missing required parameter: new_nodes", "data": {}}

    new_nodes_data = params["new_nodes"]

    if not isinstance(new_nodes_data, list) or len(new_nodes_data) == 0:
        return {"success": False, "message": "new_nodes must be a non-empty list", "data": {}}

    # Validate each node has a node_id and extract IDs
    into: list[str] = []
    for node_data in new_nodes_data:
        if "node_id" not in node_data:
            return {
                "success": False,
                "message": "Each new node must have a node_id",
                "data": {},
            }
        into.append(node_data["node_id"])

    client = CascadeClient.__new__(CascadeClient)
    client._storage = storage

    r = client.split(params["parent_id"], into, reason=params.get("reason", ""))
    return {
        "success": r.success,
        "message": r.message,
        "data": r.data,
        **({"code": r.code} if r.code else {}),
    }
