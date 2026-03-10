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

"""Edit Node Tool.

Edit an existing node's properties including promise, state, and context.
This is a unified tool that combines multiple update operations.
"""

from typing import Any

from cascade.core.state import NodeState
from cascade.storage.graph_storage import GraphStorage


def _update_context(node: Any, params: dict[str, Any]) -> bool:
    """Update node context based on params. Returns True if context was updated."""
    critical = params.get("critical")
    summary = params.get("summary")
    artifacts = params.get("artifacts")
    merge_mode = params.get("context_merge", "merge")

    if critical is None and summary is None and artifacts is None:
        return False

    if not hasattr(node, "_context_data"):
        node._context_data = {"critical": {}, "summary": "", "artifacts": {}}

    ctx = node._context_data

    if node.context is not None:
        if hasattr(node.context, "critical"):
            ctx["critical"] = dict(node.context.critical or {})
        if hasattr(node.context, "summary"):
            ctx["summary"] = node.context.summary or ""
        if hasattr(node.context, "artifacts"):
            ctx["artifacts"] = dict(node.context.artifacts or {})

    if merge_mode == "replace":
        if critical is not None:
            ctx["critical"] = dict(critical)
        if summary is not None:
            ctx["summary"] = summary
        if artifacts is not None:
            ctx["artifacts"] = dict(artifacts)
    elif merge_mode == "append":
        if critical is not None and isinstance(critical, dict):
            ctx["critical"].update(critical)
        if summary is not None:
            ctx["summary"] = (ctx["summary"] + "\n" + summary).strip()
        if artifacts is not None and isinstance(artifacts, dict):
            ctx["artifacts"].update(artifacts)
    else:
        if critical is not None and isinstance(critical, dict):
            ctx["critical"].update(critical)
        if summary is not None:
            if ctx["summary"]:
                ctx["summary"] = ctx["summary"] + "\n" + summary
            else:
                ctx["summary"] = summary
        if artifacts is not None and isinstance(artifacts, dict):
            ctx["artifacts"].update(artifacts)

    if node.context is not None:
        if hasattr(node.context, "critical"):
            node.context.critical = ctx["critical"]
        if hasattr(node.context, "summary"):
            node.context.summary = ctx["summary"]
        if hasattr(node.context, "artifacts"):
            node.context.artifacts = ctx["artifacts"]

    return True


def edit_node(storage: GraphStorage, params: dict[str, Any]) -> dict[str, Any]:
    """Edit an existing node's properties.

    Automatically handles locking, loading, saving.

    This is a unified tool for updating node properties. You can update:
    - promise: What this node promises to output
    - state: Node state (with automatic dependency handling)
    - context: Critical/summary/artifacts data

    Args:
        storage: GraphStorage instance
        params: Dictionary containing:
            - node_id (str, required): ID of the node to edit
            - promise (str, optional): New promise value
            - state (str, optional): New state (READY/ACTIVE/COMPLETED/FAILED/CANCELLED)
            - critical (dict, optional): Critical context to merge/set
            - summary (str, optional): Summary text to append/set
            - artifacts (dict, optional): Artifacts to merge/set
            - context_merge (str, optional): How to merge context ("replace"/"merge"/"append", default: "merge")

    Returns:
        Dict with:
            - success (bool): Whether the operation succeeded
            - message (str): Human-readable result message
            - data (dict): Updated node information
    """
    if "node_id" not in params:
        return {
            "success": False,
            "message": "Missing required parameter: node_id",
            "data": {},
        }

    node_id = params["node_id"]

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

            node = cascade.nodes[node_id]
            changes = []

            if "state" in params:
                new_state_str = params["state"]
                try:
                    new_state = NodeState[new_state_str.upper()]
                except KeyError:
                    valid = [s.name for s in NodeState]
                    return {
                        "success": False,
                        "message": f"Invalid state: {new_state_str}. Valid: {valid}",
                        "data": {},
                    }

                old_state = node.state

                if not old_state.can_transition_to(new_state):
                    return {
                        "success": False,
                        "message": f"Invalid transition: {old_state.name} -> {new_state.name}",
                        "data": {},
                    }

                node.update_state(new_state)
                changes.append(f"state: {old_state.name} -> {new_state.name}")

                if new_state == NodeState.COMPLETED:
                    for dependent in cascade.get_dependents(node_id):
                        if hasattr(dependent, "decrement_in_degree"):
                            dependent.decrement_in_degree()

            context_updated = _update_context(node, params)
            if context_updated:
                changes.append("context updated")

            if not changes:
                return {
                    "success": True,
                    "message": f"No changes made to node {node_id}",
                    "data": {"node_id": node_id},
                }

            storage.save(cascade)

            return {
                "success": True,
                "message": f"Node {node_id} updated: {', '.join(changes)}",
                "data": {
                    "node_id": node_id,
                    "state": node.state.name,
                },
            }

    except Exception as e:
        return {
            "success": False,
            "message": f"Operation failed: {e}",
            "data": {},
        }
