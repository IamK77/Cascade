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

"""List Nodes Tool — thin wrapper delegating to CascadeClient."""

from typing import Any

from cascade.client import CascadeClient
from cascade.storage.graph_storage import GraphStorage


def list_nodes(storage: GraphStorage, params: dict[str, Any]) -> dict[str, Any]:
    """List all nodes in the DAG with basic information.

    Args:
        storage: GraphStorage instance
        params: Dictionary containing:
            - state_filter (str, optional): Filter by state
            - include_pending_only (bool, optional): Only show PENDING nodes
    """
    client = CascadeClient.__new__(CascadeClient)
    client._storage = storage

    r = client._nodes_inner(
        state_filter=params.get("state_filter"),
        include_pending_only=params.get("include_pending_only", False),
    )
    return {
        "success": r.success,
        "message": r.message,
        "data": r.data,
        **({"code": r.code} if r.code else {}),
    }
