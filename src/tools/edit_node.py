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

"""Edit Node Tool — thin wrapper delegating to CascadeClient."""

from typing import Any

from cascade.client import CascadeClient
from cascade.storage.protocol import StorageProtocol


def edit_node(storage: StorageProtocol, params: dict[str, Any]) -> dict[str, Any]:
    """Edit an existing node's properties.

    Args:
        storage: StorageProtocol instance
        params: Dictionary containing:
            - node_id (str, required)
            - state (str, optional): New state
            - critical (dict, optional): Critical context
            - summary (str, optional): Summary text
            - artifacts (dict, optional): Artifacts
            - context_merge (str, optional): "replace"/"merge"/"append"
            - reason (str, optional): Why
    """
    if "node_id" not in params:
        return {"success": False, "message": "Missing required parameter: node_id", "data": {}}

    client = CascadeClient.__new__(CascadeClient)
    client._storage = storage

    r = client.edit(
        params["node_id"],
        state=params.get("state", ""),
        summary=params.get("summary", ""),
        critical=params.get("critical"),
        artifacts=params.get("artifacts", ""),
        context_merge=params.get("context_merge", "merge"),
        reason=params.get("reason", ""),
    )
    return {
        "success": r.success,
        "message": r.message,
        "data": r.data,
        **({"code": r.code} if r.code else {}),
    }
