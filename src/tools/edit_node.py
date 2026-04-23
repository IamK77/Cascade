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

"""Edit Node Tool."""

from typing import Any

from cascade.core.node import Node
from cascade.core.state import NodeState
from cascade.storage.graph_storage import GraphStorage
from cascade.types import Context


def _update_context(node: Node, params: dict[str, Any]) -> bool:
    """Update node context based on params. Returns True if context was updated."""
    critical = params.get("critical")
    summary = params.get("summary")
    artifacts = params.get("artifacts")
    merge_mode = params.get("context_merge", "merge")

    if critical is None and summary is None and artifacts is None:
        return False

    # Ensure node has a context object
    if node.context is None:
        node.context = Context()

    ctx = node.context

    if merge_mode == "replace":
        if critical is not None:
            ctx.critical = dict(critical)
        if summary is not None:
            ctx.summary = summary
        if artifacts is not None:
            ctx.artifacts = str(artifacts)
    elif merge_mode == "append":
        if critical is not None and isinstance(critical, dict):
            ctx.critical.update(critical)
        if summary is not None:
            ctx.summary = (ctx.summary + "\n" + summary).strip()
        if artifacts is not None:
            ctx.artifacts = str(artifacts)
    else:  # merge (default)
        if critical is not None and isinstance(critical, dict):
            ctx.critical.update(critical)
        if summary is not None:
            if ctx.summary:
                ctx.summary = ctx.summary + "\n" + summary
            else:
                ctx.summary = summary
        if artifacts is not None:
            ctx.artifacts = str(artifacts)

    return True


def edit_node(storage: GraphStorage, params: dict[str, Any]) -> dict[str, Any]:
    """Edit an existing node's properties.

    Args:
        storage: GraphStorage instance
        params: Dictionary containing:
            - node_id (str, required)
            - state (str, optional): New state
            - critical (dict, optional): Critical context
            - summary (str, optional): Summary text
            - artifacts (dict, optional): Artifacts
            - context_merge (str, optional): "replace"/"merge"/"append"
    """
    if "node_id" not in params:
        return {"success": False, "message": "Missing required parameter: node_id", "data": {}}

    node_id = params["node_id"]

    try:
        with storage.lock():
            from cascade.core.cascade import Cascade

            cascade = storage.load() or Cascade()

            if node_id not in cascade.nodes:
                return {"success": False, "message": f"Node {node_id} not found", "data": {}}

            node = cascade.nodes[node_id]
            changes: list[str] = []

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
                    cascade.notify_completion(node_id)

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
            from cascade.events import EventType

            storage.events.emit(
                EventType.NODE_EDITED,
                node_id=node_id,
                changes=changes,
                reason=params.get("reason", ""),
            )
            return {
                "success": True,
                "message": f"Node {node_id} updated: {', '.join(changes)}",
                "data": {"node_id": node_id, "state": node.state.name},
            }

    except Exception as e:
        return {"success": False, "message": f"Operation failed: {e}", "data": {}}
