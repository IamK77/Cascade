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

"""Rework operation — derive a corrective node from upstream feedback.

When a downstream agent discovers that an upstream node's output is
inadequate, it doesn't "go back" — it derives a new corrective node
that depends on the original (so the corrective agent can see what
was wrong) and wires it into the requesting node's dependencies.

This is the Cascade equivalent of Go's context.WithValue — you never
mutate the parent, you derive a new child that carries new information
forward.
"""

from dataclasses import dataclass

from cascade.core.node import Node
from cascade.core.state import NodeState
from cascade.operations.base import NodeOperation, OperationResult
from cascade.types import Context, Contract


@dataclass(frozen=True)
class ReworkResult:
    """Typed payload for ReworkOperation success."""

    corrective_node_id: str
    requesting_node_id: str
    source_node_id: str


class ReworkOperation(NodeOperation):
    """Derive a corrective node when downstream feedback indicates
    that an upstream node's output needs revision.

    The operation atomically:
    1. Creates a corrective node (with the feedback reason as context).
    2. Adds edge: source → corrective (so corrective agent sees original output).
    3. Adds edge: corrective → requester (requester waits for correction).
    4. Releases the requesting node (ACTIVE → READY → PENDING).

    The result is a forward-growing DAG — no reverse edges, no cycles.
    """

    def execute(
        self,
        requesting_node_id: str,
        source_node_id: str,
        corrective_node_id: str,
        reason: str,
        source_contract: Contract,
        corrective_contract: Contract,
    ) -> OperationResult[ReworkResult]:
        """Execute the rework operation.

        Args:
            requesting_node_id: The ACTIVE node that discovered the problem.
            source_node_id: The COMPLETED upstream node whose output is wrong.
            corrective_node_id: ID for the new corrective node.
            reason: Why rework is needed (becomes the corrective node's context).
            source_contract: Contract on edge source → corrective
                (what the corrective node expects from the original output).
            corrective_contract: Contract on edge corrective → requester
                (what the requester expects from the corrective work).
        """
        # Validate requesting node
        valid, error = self._validate_node_exists(requesting_node_id)
        if not valid:
            assert error is not None
            return OperationResult(success=False, affected_nodes=[], message=error)

        requester = self._cascade.nodes[requesting_node_id]
        if requester.state != NodeState.ACTIVE:
            return OperationResult(
                success=False, affected_nodes=[],
                message=f"Requesting node '{requesting_node_id}' must be ACTIVE (current: {requester.state.name})",
            )

        # Validate source node
        valid, error = self._validate_node_exists(source_node_id)
        if not valid:
            assert error is not None
            return OperationResult(success=False, affected_nodes=[], message=error)

        source = self._cascade.nodes[source_node_id]
        if source.state != NodeState.COMPLETED:
            return OperationResult(
                success=False, affected_nodes=[],
                message=f"Source node '{source_node_id}' must be COMPLETED (current: {source.state.name})",
            )

        # Validate corrective node doesn't exist
        if corrective_node_id in self._cascade.nodes:
            return OperationResult(
                success=False, affected_nodes=[],
                message=f"Corrective node '{corrective_node_id}' already exists",
            )

        # Validate source is actually an upstream dependency of requester
        if not self._cascade.has_dependency(requesting_node_id, source_node_id):
            return OperationResult(
                success=False, affected_nodes=[],
                message=f"'{source_node_id}' is not a dependency of '{requesting_node_id}'",
            )

        try:
            # 1. Create corrective node with feedback as context
            corrective_context = Context(
                summary=reason,
                critical={"rework_source": source_node_id, "rework_reason": reason},
            )
            corrective_node = Node(
                id=corrective_node_id,
                context=corrective_context,
            )
            self._cascade.add_node(corrective_node)

            # 2. source → corrective (corrective agent sees original output)
            self._cascade.add_edge(
                source_node_id, corrective_node_id,
                contract=source_contract,
            )

            # 3. corrective → requester (requester waits for correction)
            self._cascade.add_edge(
                corrective_node_id, requesting_node_id,
                contract=corrective_contract,
            )
            # add_edge triggers _update_readiness on requester:
            #   requester has a new uncompleted dep → ACTIVE is untouched
            #   (readiness only affects PENDING/READY nodes)

            # 4. Release requester: ACTIVE → READY (via state machine),
            #    then _update_readiness detects pending dep → PENDING
            requester.update_state(NodeState.READY)
            self._cascade._update_readiness(requesting_node_id)

            return OperationResult(
                success=True,
                affected_nodes=[corrective_node_id, requesting_node_id, source_node_id],
                message=(
                    f"Rework requested: '{corrective_node_id}' created to correct "
                    f"'{source_node_id}', '{requesting_node_id}' will resume after correction"
                ),
                data=ReworkResult(
                    corrective_node_id=corrective_node_id,
                    requesting_node_id=requesting_node_id,
                    source_node_id=source_node_id,
                ),
            )

        except ValueError as e:
            return OperationResult(
                success=False, affected_nodes=[],
                message=f"Rework failed: {e}",
            )
