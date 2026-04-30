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

"""Finish Task Tool — thin wrapper delegating to CascadeClient."""

from typing import Any

from cascade.client import CascadeClient
from cascade.storage.protocol import StorageProtocol


def finish_task(storage: StorageProtocol, params: dict[str, Any]) -> dict[str, Any]:
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
    summary = params.get("summary") or params.get("result")  # 'result' for backward compat
    critical = params.get("critical")
    artifacts = params.get("artifacts")
    should_cascade = params.get("cascade", False)

    client = CascadeClient.__new__(CascadeClient)
    client._storage = storage

    if is_release:
        r = client.release(task_id, reason=summary or "")
    elif is_success:
        r = client.complete(
            task_id,
            summary=summary or "",
            critical=critical,
            artifacts=artifacts or "",
        )
    else:
        r = client.fail(task_id, reason=summary or "", cascade=should_cascade)

    return {
        "success": r.success,
        "message": r.message,
        "data": r.data,
        **({"code": r.code} if r.code else {}),
    }
