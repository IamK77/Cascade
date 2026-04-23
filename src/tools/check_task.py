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

"""Check Task Tool — pull-based cancellation interface."""

from typing import Any

from cascade.storage.graph_storage import GraphStorage


def check_task(storage: GraphStorage, params: dict[str, Any]) -> dict[str, Any]:
    """Check whether a claimed task is still valid.

    This is the pull-based cancellation interface. The agent framework
    (not the agent itself) calls this to verify a task claim is still
    active before continuing work.

    Args:
        storage: GraphStorage instance
        params: Dictionary containing:
            - task_id (str, required): The task to check
    """
    task_id = params.get("task_id")
    if not task_id:
        return {"success": False, "message": "Missing required parameter: task_id", "data": {}}

    token = storage.tokens.check(task_id)
    if token is None:
        return {
            "success": True,
            "message": f"No active claim for task {task_id}",
            "data": {"task_id": task_id, "valid": False, "reason": "no_token"},
        }

    return {
        "success": True,
        "message": f"Task {task_id}: {'valid' if token.valid else 'invalidated'}",
        "data": {
            "task_id": token.node_id,
            "agent_id": token.agent_id,
            "valid": token.valid,
            "claimed_at": token.claimed_at,
            "reason": token.reason,
            "invalidated_at": token.invalidated_at,
        },
    }
