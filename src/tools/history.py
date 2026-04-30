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

"""History Tool — thin wrapper delegating to CascadeClient."""

from typing import Any

from cascade.client import CascadeClient
from cascade.storage.protocol import StorageProtocol


def history(storage: StorageProtocol, params: dict[str, Any]) -> dict[str, Any]:
    """Query the event history.

    Args:
        storage: StorageProtocol instance
        params: Dictionary containing:
            - node_id (str, optional): Filter events for a specific node
            - event_type (str, optional): Filter by event type
            - last_n (int, optional): Return only the last N events
            - summary (bool, optional): If True, return event count by type
    """
    client = CascadeClient(storage)

    r = client.history(
        node_id=params.get("node_id", ""),
        event_type=params.get("event_type", ""),
        last_n=params.get("last_n", 0),
        summary=params.get("summary", False),
    )
    return r.to_dict()
