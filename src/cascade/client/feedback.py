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

"""Client mixin — feedback operations (rework)."""

from __future__ import annotations

from cascade import tips
from cascade.client.base import ClientBase
from cascade.events import EventType
from cascade.operations.rework import ReworkOperation
from cascade.types import Contract, ErrorCode, Result

_REQUIRED_PARAMS = [
    "corrective",
    "reason",
    "agent_id",
    "source_expectation",
    "source_promise",
    "corrective_expectation",
    "corrective_promise",
]


class FeedbackMixin(ClientBase):
    """Feedback operations: rework."""

    def rework(
        self,
        source: str,
        corrective: str,
        reason: str,
        agent_id: str,
        *,
        source_expectation: str,
        source_promise: str,
        corrective_expectation: str,
        corrective_promise: str,
    ) -> Result:
        """Request rework of an upstream node's output."""
        params = {
            "source": source,
            "corrective": corrective,
            "reason": reason,
            "agent_id": agent_id,
            "source_expectation": source_expectation,
            "source_promise": source_promise,
            "corrective_expectation": corrective_expectation,
            "corrective_promise": corrective_promise,
        }
        for name, value in params.items():
            if not value:
                return Result(
                    success=False,
                    message=f"Missing required parameter: {name}",
                    code=ErrorCode.INVALID_INPUT,
                )

        source_contract = Contract(
            expectation=source_expectation,
            promise=source_promise,
        )
        corrective_contract = Contract(
            expectation=corrective_expectation,
            promise=corrective_promise,
        )

        try:
            with self._mutate() as tx:
                active_node = tx.graph.find_agent_active_task(agent_id)
                if not active_node:
                    return Result(
                        success=False,
                        message=f"Agent '{agent_id}' has no active task to request rework from",
                        code=ErrorCode.TASK_NOT_ACTIVE,
                    )

                operation = ReworkOperation(tx.graph)
                result = operation.execute(
                    requesting_node_id=active_node.id,
                    source_node_id=source,
                    corrective_node_id=corrective,
                    reason=reason,
                    source_contract=source_contract,
                    corrective_contract=corrective_contract,
                )

                if result.success:
                    active_node.agent_id = None
                    self._storage.tokens.invalidate(active_node.id, reason="rework_requested")
                    tx.emit(
                        EventType.REWORK_REQUESTED,
                        source_node_id=source,
                        corrective_node_id=corrective,
                        requesting_node_id=active_node.id,
                        agent_id=agent_id,
                        reason=reason,
                        source_contract={
                            "expectation": source_expectation,
                            "promise": source_promise,
                        },
                        corrective_contract={
                            "expectation": corrective_expectation,
                            "promise": corrective_promise,
                        },
                    )
                    tx.save()

                message = result.message
                if result.success:
                    rework_tips = tips.on_rework(
                        active_node_id=active_node.id,
                        corrective_node_id=corrective,
                    )
                    message = tips.append_tips(message, rework_tips)

                return Result(
                    success=result.success,
                    message=message,
                    data={
                        "corrective_node_id": result.data.corrective_node_id
                        if result.data
                        else None,
                        "requesting_node_id": result.data.requesting_node_id
                        if result.data
                        else None,
                        "source_node_id": result.data.source_node_id if result.data else None,
                        "affected_nodes": result.affected_nodes,
                    },
                )

        except Exception as e:
            return Result(
                success=False, message=f"Operation failed: {e}", code=ErrorCode.INTERNAL_ERROR
            )
