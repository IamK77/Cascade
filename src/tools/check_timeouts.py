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

"""Check Timeouts Tool — thin wrapper delegating to CascadeClient."""

from typing import Any

from cascade.client import CascadeClient
from cascade.storage.protocol import StorageProtocol


def check_timeouts(storage: StorageProtocol, params: dict[str, Any]) -> dict[str, Any]:
    """Scan for timed-out tasks and release them.

    Args:
        storage: StorageProtocol instance
        params: Dictionary containing:
            - default_timeout (float, optional): Timeout in seconds applied
              to ACTIVE tasks that don't have a per-task timeout set.
    """
    client = CascadeClient.__new__(CascadeClient)
    client._storage = storage

    r = client.check_timeouts(default_timeout=params.get("default_timeout"))
    return {
        "success": r.success,
        "message": r.message,
        "data": r.data,
        **({"code": r.code} if r.code else {}),
    }
