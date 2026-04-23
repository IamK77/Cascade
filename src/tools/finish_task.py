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
from cascade.types import Context


def finish_task(storage: GraphStorage, params: dict[str, Any]) -> dict[str, Any]:
    """Mark a task as finished.

    Three outcomes:
    1. Complete successfully: ACTIVE -> COMPLETED, unblock dependents
    2. Fail: ACTIVE -> FAILED, optionally cascade
    3. Release: ACTIVE -> READY, return to pool

    Context output (for success):
        The agent's work product flows downstream through context propagation.
        - summary (str): Brief description of what was accomplished.
          Propagates to children and grandchildren (distance <= 2).
        - critical (dict): Key-value data that propagates indefinitely
          to ALL descendants. Use for structured output that downstream
          tasks need (e.g., {"api_endpoints": [...], "schema_version": 2}).
        - artifacts (str): Detailed output content. Persisted to file,
          path reference propagates indefinitely.

        If the node has no context yet, one is created automatically.
        Your output IS your fulfilled promise — downstream agents receive
        it through the contracts you committed to on the edges.
    """
    if "task_id" not in params:
        return {"success": False, "message": "Missing required parameter: task_id", "data": {}}

    task_id = params["task_id"]
    is_release = params.get("release", False)
    is_success = params.get("success", True) if not is_release else params.get("success", False)
    summary = params.get("summary") or params.get("result")  # 'result' for backward compat
    critical = params.get("critical")
    artifacts = params.get("artifacts")
    should_cascade = params.get("cascade", False)

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
                if summary:
                    message += f" (reason: {summary})"

                storage.save(cascade)
                storage.tokens.invalidate(task_id, reason="released")
                from cascade.events import EventType

                storage.events.emit(EventType.TASK_RELEASED, node_id=task_id, reason=summary)
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

                # Ensure context exists — agent output must never be silently dropped
                if summary or critical or artifacts:
                    if node.context is None:
                        node.context = Context()
                    if summary:
                        node.context.summary = summary
                    if critical and isinstance(critical, dict):
                        node.context.critical.update(critical)
                    if artifacts:
                        node.context.artifacts = str(artifacts)

                unblocked = cascade.notify_completion(task_id)

                message = f"Task {task_id} completed"
                if unblocked:
                    message += f", unblocked: {unblocked}"

                storage.save(cascade)
                storage.tokens.cleanup(task_id)
                from cascade.events import EventType

                storage.events.emit(EventType.TASK_COMPLETED, node_id=task_id, unblocked=unblocked)
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
                if summary:
                    message += f": {summary}"

                storage.save(cascade)
                storage.tokens.cleanup(task_id)
                from cascade.events import EventType

                storage.events.emit(
                    EventType.TASK_FAILED,
                    node_id=task_id,
                    reason=summary,
                    affected=affected,
                    cascade=should_cascade,
                )
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
