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

"""Finish Task Tool.

Unified tool for task completion with flexible outcomes:
- success=True: Mark as COMPLETED, unblock dependents
- success=False: Mark as FAILED, optionally cascade
- release=True: Release task back to pool (ACTIVE -> READY)
"""

from typing import Any

from cascade.core.state import NodeState
from cascade.storage.graph_storage import GraphStorage


def finish_task(storage: GraphStorage, params: dict[str, Any]) -> dict[str, Any]:
    """Mark a task as finished.

    Automatically handles locking, loading, saving.

    Unified tool with three outcomes:
    1. Complete successfully: ACTIVE -> COMPLETED, unblock dependents
    2. Fail: ACTIVE -> FAILED, optionally cascade to dependents
    3. Release: ACTIVE -> READY, return to pool

    Args:
        storage: GraphStorage instance
        params: Dictionary containing:
            - task_id (str, required): ID of the task
            - success (bool, optional): True=completed, False=failed
            - release (bool, optional): If True, release back to READY instead of fail
            - result (str, optional): Result summary, error message, or release reason
            - cascade (bool, optional): If failed, also fail dependents
            - artifacts (dict, optional): Artifacts produced (for success)

    Returns:
        Dict with success, message, and data
    """
    if "task_id" not in params:
        return {
            "success": False,
            "message": "Missing required parameter: task_id",
            "data": {},
        }

    task_id = params["task_id"]
    is_release = params.get("release", False)
    is_success = params.get("success", True) if not is_release else params.get("success", False)
    result_text = params.get("result")
    should_cascade = params.get("cascade", False)
    artifacts = params.get("artifacts")

    try:
        with storage.lock():
            from cascade.core.cascade import Cascade
            cascade = storage.load() or Cascade()

            if task_id not in cascade.nodes:
                return {
                    "success": False,
                    "message": f"Task {task_id} not found",
                    "data": {},
                }

            node = cascade.nodes[task_id]

            if node.state != NodeState.ACTIVE:
                return {
                    "success": False,
                    "message": f"Task {task_id} is not active (current: {node.state.name})",
                    "data": {"state": node.state.name},
                }

            def clear_agent() -> None:
                """Clear agent assignment from node."""
                if node.agent_id:
                    node.agent_id = None

            if is_release:
                node.state = NodeState.READY
                clear_agent()

                message = f"Task {task_id} released and is now available"
                if result_text:
                    message += f" (reason: {result_text})"

                storage.save(cascade)

                return {
                    "success": True,
                    "message": message,
                    "data": {
                        "task_id": task_id,
                        "outcome": "RELEASED",
                        "state": "READY",
                    },
                }

            elif is_success:
                node.update_state(NodeState.COMPLETED)
                clear_agent()

                if result_text or artifacts:
                    if node.context is not None:
                        if result_text and hasattr(node.context, "summary"):
                            node.context.summary = result_text
                        if artifacts and hasattr(node.context, "artifacts"):
                            node.context.artifacts = str(artifacts)

                unblocked = []
                for dependent in cascade.get_dependents(task_id):
                    if hasattr(dependent, "decrement_in_degree"):
                        dependent.decrement_in_degree()
                        if dependent.state == NodeState.READY:
                            unblocked.append(dependent.id)

                message = f"Task {task_id} completed"
                if unblocked:
                    message += f", unblocked: {unblocked}"

                storage.save(cascade)

                return {
                    "success": True,
                    "message": message,
                    "data": {
                        "task_id": task_id,
                        "outcome": "COMPLETED",
                        "unblocked_tasks": unblocked,
                    },
                }

            else:
                affected = [task_id]
                clear_agent()

                if should_cascade:

                    def fail_recursive(nid: str) -> None:
                        current = cascade.nodes[nid]
                        if current.state.is_terminal():
                            return
                        current.state = NodeState.FAILED
                        current.agent_id = None
                        affected.append(nid)
                        for dep in cascade.get_dependents(nid):
                            fail_recursive(dep.id)

                    fail_recursive(task_id)

                else:
                    node.update_state(NodeState.FAILED)

                message = f"Task {task_id} failed"
                if should_cascade and len(affected) > 1:
                    message += f" (cascaded to {len(affected) - 1} dependent tasks)"
                if result_text:
                    message += f": {result_text}"

                storage.save(cascade)

                return {
                    "success": True,
                    "message": message,
                    "data": {
                        "task_id": task_id,
                        "outcome": "FAILED",
                        "affected_tasks": affected,
                        "cascade": should_cascade,
                    },
                }

    except Exception as e:
        return {
            "success": False,
            "message": f"Operation failed: {e}",
            "data": {},
        }
