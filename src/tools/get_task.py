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

"""Get Task Tool.

Get a task to work on. This is the primary entry point for agents to get work.
Returns full task information and marks it as ACTIVE.

Agent Tracking:
    - agent_id is REQUIRED
    - Prevents agents from taking multiple tasks simultaneously
    - Returns reminder if agent already has an ACTIVE task
"""

from typing import Any

from cascade.core.state import NodeState
from cascade.storage.graph_storage import GraphStorage


def get_task(storage: GraphStorage, params: dict[str, Any]) -> dict[str, Any]:
    """Get a task to work on.

    Automatically handles locking, loading, saving.

    Args:
        storage: GraphStorage instance
        params: Dictionary containing:
            - agent_id (str, required): ID of the agent requesting work
            - task_id (str, optional): Specific task to get, or omit for any available

    Returns:
        Dict with:
            - success (bool): Whether a task was found/assigned
            - message (str): Human-readable result
            - data (dict): Contains task_info with full node details
    """
    agent_id = params.get("agent_id")
    task_id = params.get("task_id")

    # agent_id is required to prevent agents from taking multiple tasks
    if not agent_id:
        return {
            "success": False,
            "message": "agent_id is required. Each agent can only hold ONE task at a time.",
            "data": {},
        }

    try:
        with storage.lock():
            from cascade.core.cascade import Cascade
            cascade = storage.load() or Cascade()

            # Check if agent already has an ACTIVE task
            # Each agent can only hold ONE task at a time
            existing_node = cascade.find_agent_active_task(agent_id)
            if existing_node:
                task_info = cascade.get_node_view(existing_node.id)
                return {
                    "success": True,
                    "message": (
                        f"You already have an active task: {existing_node.id}. "
                        f"You can only hold ONE task at a time. "
                        f"Use finish_task() to complete it before getting a new task."
                    ),
                    "data": {
                        "task_id": existing_node.id,
                        "state": "ACTIVE",
                        "task_info": task_info,
                        "reminder": True,
                        "blocked_reason": "already_has_active_task",
                    },
                }

            if task_id:
                if task_id not in cascade.nodes:
                    return {
                        "success": False,
                        "message": f"Task {task_id} not found",
                        "data": {},
                    }

                node = cascade.nodes[task_id]

                # Check if task is already assigned to another agent
                if node.agent_id and node.agent_id != agent_id and node.state == NodeState.ACTIVE:
                    return {
                        "success": False,
                        "message": f"Task {task_id} is already being executed by agent: {node.agent_id}",
                        "data": {"state": "ACTIVE", "assigned_to": node.agent_id},
                    }

                if node.state == NodeState.ACTIVE:
                    # Reassign to same agent or agent taking over
                    node.agent_id = agent_id
                    task_info = cascade.get_node_view(task_id)
                    storage.save(cascade)
                    return {
                        "success": True,
                        "message": f"Task {task_id} is already active",
                        "data": {
                            "task_id": task_id,
                            "state": "ACTIVE",
                            "task_info": task_info,
                        },
                    }

                if node.state.is_terminal():
                    return {
                        "success": False,
                        "message": f"Task {task_id} is in terminal state: {node.state.name}",
                        "data": {"state": node.state.name},
                    }

                if node.state == NodeState.PENDING:
                    return {
                        "success": False,
                        "message": f"Task {task_id} is not ready (dependencies not met, in_degree={node.in_degree})",
                        "data": {"state": "PENDING", "in_degree": node.in_degree},
                    }

                node.update_state(NodeState.ACTIVE)
                node.agent_id = agent_id

            else:
                ready_nodes = cascade.get_ready_nodes()

                if not ready_nodes:
                    active_count = sum(1 for n in cascade.nodes.values() if n.state == NodeState.ACTIVE)
                    pending_count = sum(1 for n in cascade.nodes.values() if n.state == NodeState.PENDING)

                    if active_count > 0:
                        return {
                            "success": False,
                            "message": f"No available tasks. {active_count} task(s) are executed, {pending_count} pending.",
                            "data": {"active": active_count, "pending": pending_count},
                        }
                    else:
                        return {
                            "success": False,
                            "message": f"No available tasks. All {pending_count} tasks are pending (dependencies not met).",
                            "data": {"pending": pending_count},
                        }

                node = ready_nodes[0]
                task_id = node.id
                node.update_state(NodeState.ACTIVE)
                node.agent_id = agent_id

            task_info = cascade.get_node_view(task_id)
            storage.save(cascade)

            return {
                "success": True,
                "message": f"Task {task_id} assigned (state: ACTIVE)",
                "data": {
                    "task_id": task_id,
                    "state": "ACTIVE",
                    "task_info": task_info,
                    "assigned_to": agent_id,
                },
            }

    except Exception as e:
        return {
            "success": False,
            "message": f"Operation failed: {e}",
            "data": {},
        }
