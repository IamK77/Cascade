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

"""Remove Node Tool — thin wrapper delegating to CascadeClient."""

from typing import Any

from cascade.client import CascadeClient
from cascade.storage.graph_storage import GraphStorage


def remove_node(storage: GraphStorage, params: dict[str, Any]) -> dict[str, Any]:
    """Remove a node from the DAG.

    Args:
        storage: GraphStorage instance
        params: Dictionary containing:
            - node_id (str, required)
            - cascade (bool, optional): Also remove dependents (default: False)
            - reason (str, optional): Why
    """
    if "node_id" not in params:
        return {"success": False, "message": "Missing required parameter: node_id", "data": {}}

    client = CascadeClient.__new__(CascadeClient)
    client._storage = storage

    r = client.remove(
        params["node_id"],
        cascade=params.get("cascade", False),
        reason=params.get("reason", ""),
    )
    return {"success": r.success, "message": r.message, "data": r.data}
