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

"""Check Task Tool — thin wrapper delegating to CascadeClient."""

from typing import Any

from cascade.client import CascadeClient
from cascade.storage.graph_storage import GraphStorage


def check_task(storage: GraphStorage, params: dict[str, Any]) -> dict[str, Any]:
    """Check whether a claimed task is still valid.

    Args:
        storage: GraphStorage instance
        params: Dictionary containing:
            - task_id (str, required): The task to check
    """
    task_id = params.get("task_id")
    if not task_id:
        return {"success": False, "message": "Missing required parameter: task_id", "data": {}}

    client = CascadeClient.__new__(CascadeClient)
    client._storage = storage

    r = client.check(task_id)
    return {"success": r.success, "message": r.message, "data": r.data}
