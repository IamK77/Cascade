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

"""Rework Tool.

Request corrective work when an upstream node's output is inadequate.
This creates a corrective node, wires it into the graph, and releases
the current task to wait for the correction.

The graph grows forward — no reverse edges, no cycles.
"""

from typing import Any

from cascade.storage.graph_storage import GraphStorage
from cascade.types import Contract


def rework(storage: GraphStorage, params: dict[str, Any]) -> dict[str, Any]:
    """Request rework of an upstream node's output.

    When an agent discovers that a dependency's output is wrong or
    incomplete, it calls this tool to derive a corrective node.
    The agent's current task is released and will resume after
    the corrective work is completed.

    Args:
        storage: GraphStorage instance
        params: Dictionary containing:
            - source_node_id (str, required): The upstream node whose output needs correction
            - corrective_node_id (str, required): ID for the new corrective node
            - reason (str, required): Why rework is needed (becomes corrective node's context)
            - source_expectation (str, required): What the corrective node can expect
              from the original source (e.g., "original analysis output")
            - source_promise (str, required): What the source promises to the corrective
              node (e.g., "the original analysis for review")
            - corrective_expectation (str, required): What the requesting node expects
              from the corrective work (e.g., "revised analysis addressing X issue")
            - corrective_promise (str, required): What the corrective node promises
              (e.g., "corrected analysis with Y fixed")
            - agent_id (str, required): The agent requesting rework (must own the active task)

    Returns:
        Dict with success, message, data.
    """
    # Validate required params
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

    source_node_id = params["source_node_id"]
    corrective_node_id = params["corrective_node_id"]
    reason = params["reason"]
    agent_id = params["agent_id"]

    source_contract = Contract(
        expectation=params["source_expectation"],
        promise=params["source_promise"],
    )
    corrective_contract = Contract(
        expectation=params["corrective_expectation"],
        promise=params["corrective_promise"],
    )

    try:
        with storage.lock():
            from cascade.core.cascade import Cascade
            from cascade.operations.rework import ReworkOperation

            cascade = storage.load() or Cascade()

            # Find the agent's active task
            active_node = cascade.find_agent_active_task(agent_id)
            if not active_node:
                return {
                    "success": False,
                    "message": f"Agent '{agent_id}' has no active task to request rework from",
                    "data": {},
                }

            operation = ReworkOperation(cascade)
            result = operation.execute(
                requesting_node_id=active_node.id,
                source_node_id=source_node_id,
                corrective_node_id=corrective_node_id,
                reason=reason,
                source_contract=source_contract,
                corrective_contract=corrective_contract,
            )

            if result.success:
                active_node.agent_id = None
                storage.save(cascade)
                storage.tokens.invalidate(active_node.id, reason="rework_requested")
                from cascade.events import EventType

                storage.events.emit(
                    EventType.REWORK_REQUESTED,
                    source_node_id=source_node_id,
                    corrective_node_id=corrective_node_id,
                    requesting_node_id=active_node.id,
                    agent_id=agent_id,
                    reason=reason,
                )

            return {
                "success": result.success,
                "message": result.message,
                "data": {
                    "corrective_node_id": result.data.corrective_node_id if result.data else None,
                    "requesting_node_id": result.data.requesting_node_id if result.data else None,
                    "source_node_id": result.data.source_node_id if result.data else None,
                    "affected_nodes": result.affected_nodes,
                },
            }

    except Exception as e:
        return {"success": False, "message": f"Operation failed: {e}", "data": {}}
