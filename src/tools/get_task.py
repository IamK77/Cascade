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

"""Get Task Tool — thin wrapper delegating to CascadeClient."""

from typing import Any

from cascade.client import CascadeClient
from cascade.storage.protocol import StorageProtocol


def get_task(storage: StorageProtocol, params: dict[str, Any]) -> dict[str, Any]:
    """Get a task to work on.

    Args:
        storage: StorageProtocol instance
        params: Dictionary containing:
            - agent_id (str, required): ID of the agent requesting work
            - task_id (str, optional): Specific task to get
            - timeout (float, optional): Timeout in seconds for this claim.
            - cancel_notifier (CancelNotifier, optional): Push notification on cancellation.
    """
    agent_id = params.get("agent_id")
    task_id = params.get("task_id")
    timeout = params.get("timeout")
    cancel_notifier = params.get("cancel_notifier")

    if not agent_id:
        return {
            "success": False,
            "message": "agent_id is required. Each agent can only hold ONE task at a time.",
            "data": {},
        }

    client = CascadeClient(storage)

    r = client._claim_inner(
        agent_id,
        task_id,
        timeout=timeout,
        cancel_notifier=cancel_notifier,
    )
    return r.to_dict()
