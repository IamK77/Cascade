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

"""Rework Tool — thin wrapper delegating to CascadeClient."""

from typing import Any

from cascade.client import CascadeClient
from cascade.storage.protocol import StorageProtocol


def rework(storage: StorageProtocol, params: dict[str, Any]) -> dict[str, Any]:
    """Request rework of an upstream node's output.

    Args:
        storage: StorageProtocol instance
        params: Dictionary containing:
            - source_node_id (str, required)
            - corrective_node_id (str, required)
            - reason (str, required)
            - agent_id (str, required)
            - source_expectation (str, required)
            - source_promise (str, required)
            - corrective_expectation (str, required)
            - corrective_promise (str, required)
    """
    required = [
        "source_node_id",
        "corrective_node_id",
        "reason",
        "agent_id",
        "source_expectation",
        "source_promise",
        "corrective_expectation",
        "corrective_promise",
    ]
    for field in required:
        if not params.get(field):
            return {"success": False, "message": f"Missing required parameter: {field}", "data": {}}

    client = CascadeClient(storage)

    r = client.rework(
        source=params["source_node_id"],
        corrective=params["corrective_node_id"],
        reason=params["reason"],
        agent_id=params["agent_id"],
        source_expectation=params["source_expectation"],
        source_promise=params["source_promise"],
        corrective_expectation=params["corrective_expectation"],
        corrective_promise=params["corrective_promise"],
    )
    return r.to_dict()
