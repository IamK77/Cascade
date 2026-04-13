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

"""Finish Task Tool."""

from typing import Any

from cascade.core.state import NodeState
from cascade.storage.graph_storage import GraphStorage


def finish_task(storage: GraphStorage, params: dict[str, Any]) -> dict[str, Any]:
    """Mark a task as finished.

    Three outcomes:
    1. Complete successfully: ACTIVE -> COMPLETED, unblock dependents
    2. Fail: ACTIVE -> FAILED, optionally cascade
    3. Release: ACTIVE -> READY, return to pool
    """
    if "task_id" not in params:
        return {"success": False, "message": "Missing required parameter: task_id", "data": {}}

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
                return {"success": False, "message": f"Task {task_id} not found", "data": {}}

            node = cascade.nodes[task_id]

            if node.state != NodeState.ACTIVE:
                return {
                    "success": False,
                    "message": f"Task {task_id} is not active (current: {node.state.name})",
                    "data": {"state": node.state.name},
                }

            if is_release:
                node.update_state(NodeState.READY)
                node.agent_id = None
                node.claimed_at = None
                node.timeout = None

                message = f"Task {task_id} released and is now available"
                if result_text:
                    message += f" (reason: {result_text})"

                storage.save(cascade)
                return {
                    "success": True,
                    "message": message,
                    "data": {"task_id": task_id, "outcome": "RELEASED", "state": "READY"},
                }

            elif is_success:
                node.update_state(NodeState.COMPLETED)
                node.agent_id = None
                node.claimed_at = None
                node.timeout = None

                if result_text and node.context is not None:
                    node.context.summary = result_text
                if artifacts and node.context is not None:
                    node.context.artifacts = str(artifacts)

                # Use centralized readiness management
                unblocked = cascade.notify_completion(task_id)

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
                node.agent_id = None

                if should_cascade:
                    def fail_recursive(nid: str) -> None:
                        current = cascade.nodes[nid]
                        if current.state.is_terminal():
                            return
                        current.update_state(NodeState.FAILED)
                        current.agent_id = None
                        current.claimed_at = None
                        current.timeout = None
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
        return {"success": False, "message": f"Operation failed: {e}", "data": {}}
