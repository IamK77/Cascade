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

"""List Nodes Tool.

List all nodes in the DAG with their basic information.
Use this to get an overview of all tasks in the system.
"""

from typing import Any

from cascade.storage.graph_storage import GraphStorage


def list_nodes(storage: GraphStorage, params: dict[str, Any]) -> dict[str, Any]:
    """List all nodes in the DAG.

    Automatically handles locking, loading (read-only, no save needed).

    Args:
        storage: GraphStorage instance
        params: Dictionary containing optional filters:
            - state_filter (str, optional): Only return nodes in this state
            - include_pending_only (bool, optional): Only return PENDING nodes

    Returns:
        Dict with:
            - success (bool): Whether the operation succeeded
            - message (str): Human-readable result message
            - data (dict): Contains:
                - nodes: List of node dicts with id, state, promise, in_degree
                - count: Total number of nodes
                - by_state: Dict grouping node IDs by state
    """
    state_filter = params.get("state_filter")
    include_pending_only = params.get("include_pending_only", False)

    try:
        with storage.lock():
            from cascade.core.cascade import Cascade
            cascade = storage.load() or Cascade()

            nodes_list: list[dict[str, Any]] = []
            by_state: dict[str, list[str]] = {}

            for node_id, node in cascade.nodes.items():
                if state_filter and node.state.name != state_filter:
                    continue
                if include_pending_only and node.state.name != "PENDING":
                    continue

                node_info = {
                    "id": node.id,
                    "state": node.state.name,
                    "in_degree": node.in_degree,
                }

                nodes_list.append(node_info)

                state_name = node.state.name
                if state_name not in by_state:
                    by_state[state_name] = []
                by_state[state_name].append(node_id)

            if state_filter or include_pending_only:
                by_state = {}
                for node_info in nodes_list:
                    state_name = str(node_info["state"])
                    if state_name not in by_state:
                        by_state[state_name] = []
                    by_state[state_name].append(str(node_info["id"]))

            return {
                "success": True,
                "message": f"Listed {len(nodes_list)} nodes",
                "data": {
                    "nodes": nodes_list,
                    "count": len(nodes_list),
                    "by_state": by_state,
                },
            }

    except Exception as e:
        return {
            "success": False,
            "message": f"Failed to list nodes: {e}",
            "data": {
                "nodes": [],
                "count": 0,
                "by_state": {},
            },
        }
