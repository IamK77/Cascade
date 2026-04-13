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

"""Check Timeouts Tool.

Scan ACTIVE tasks and release any that have exceeded their timeout.
This is a cooperative timeout — it must be called periodically by
a supervisor, watchdog, or another agent.
"""

import time
from typing import Any

from cascade.core.state import NodeState
from cascade.storage.graph_storage import GraphStorage


def check_timeouts(storage: GraphStorage, params: dict[str, Any]) -> dict[str, Any]:
    """Scan for timed-out tasks and release them.

    Any ACTIVE task that has exceeded its timeout is released back to
    READY, clearing the agent assignment. This allows other agents to
    pick up stalled work.

    Args:
        storage: GraphStorage instance
        params: Dictionary containing:
            - default_timeout (float, optional): Timeout in seconds applied
              to ACTIVE tasks that don't have a per-task timeout set.
              If omitted, only tasks with explicit timeouts are checked.

    Returns:
        Dict with success, message, data (released task IDs).
    """
    default_timeout = params.get("default_timeout")

    try:
        with storage.lock():
            from cascade.core.cascade import Cascade
            cascade = storage.load() or Cascade()

            now = time.time()
            released: list[dict[str, Any]] = []

            for node in cascade.nodes.values():
                if node.state != NodeState.ACTIVE:
                    continue
                if node.claimed_at is None:
                    continue

                # Determine effective timeout
                effective_timeout = node.timeout or default_timeout
                if effective_timeout is None:
                    continue

                elapsed = now - node.claimed_at
                if elapsed < effective_timeout:
                    continue

                # Release the stalled task
                old_agent = node.agent_id
                node.update_state(NodeState.READY)
                node.agent_id = None
                node.claimed_at = None
                node.timeout = None

                released.append({
                    "task_id": node.id,
                    "agent_id": old_agent,
                    "elapsed_seconds": round(elapsed, 1),
                    "timeout_seconds": effective_timeout,
                })
                from cascade.events import EventType
                storage.events.emit(EventType.TASK_TIMED_OUT, node_id=node.id,
                                    agent_id=old_agent, elapsed=round(elapsed, 1))

            if released:
                storage.save(cascade)

            return {
                "success": True,
                "message": f"Released {len(released)} timed-out task(s)" if released else "No timed-out tasks found",
                "data": {
                    "released": released,
                    "count": len(released),
                },
            }

    except Exception as e:
        return {"success": False, "message": f"Operation failed: {e}", "data": {}}
