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

"""Context propagation logic for information flow through the Cascade.

Propagation rules (owned here, not by Context):
    - CRITICAL (KV):  propagates indefinitely through ancestor chain.
    - SUMMARY (text): propagates within SUMMARY_MAX_DISTANCE hops.
    - ARTIFACTS (str): propagates indefinitely through ancestor chain.

Each ancestor's contribution is kept separate as a ContextEntry with
full provenance (node_id, path, distance). Direct parents also carry
the contract (expectation, promise) from the connecting edge.
"""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

from cascade.types import ContextEntry

if TYPE_CHECKING:
    from cascade.core.cascade import Cascade

SUMMARY_MAX_DISTANCE = 2


class ContextPropagator:
    """Collects attributed context from a node's ancestors."""

    def __init__(self, cascade: Cascade):
        self._cascade = cascade

    def collect_context_at(self, node_id: str) -> list[ContextEntry]:
        """Collect context from all ancestors with provenance.

        BFS walks up the entire ancestor chain. For each ancestor with
        context, produces a ContextEntry containing:
            - node_id, state, distance, path (always)
            - expectation, promise (direct parents only)
            - critical, artifacts (any distance)
            - summary (within SUMMARY_MAX_DISTANCE only)
        """
        if node_id not in self._cascade.nodes:
            raise ValueError(f"Node {node_id} not found")

        entries: list[ContextEntry] = []
        visited: set[str] = {node_id}
        path_to: dict[str, list[str]] = {}
        queue: deque[tuple[str, int]] = deque([(node_id, 0)])

        while queue:
            current_id, distance = queue.popleft()

            if distance > 0:
                node = self._cascade.nodes[current_id]
                if node.context:
                    entry_critical = dict(node.context.critical) if node.context.critical else {}
                    entry_summary = node.context.summary if distance <= SUMMARY_MAX_DISTANCE else ""
                    entry_artifacts = node.context.artifacts

                    if entry_critical or entry_summary or entry_artifacts:
                        expectation = ""
                        promise = ""
                        if distance == 1:
                            contract = self._cascade.get_contract(current_id, node_id)
                            if contract:
                                expectation = contract.expectation
                                promise = contract.promise

                        entries.append(ContextEntry(
                            node_id=current_id,
                            state=node.state.name,
                            distance=distance,
                            path=path_to[current_id],
                            expectation=expectation,
                            promise=promise,
                            summary=entry_summary,
                            critical=entry_critical,
                            artifacts=entry_artifacts,
                        ))

            for dependency in self._cascade.get_dependencies(current_id):
                if dependency.id not in visited:
                    visited.add(dependency.id)
                    path_to[dependency.id] = [dependency.id] + (path_to.get(current_id, []))
                    queue.append((dependency.id, distance + 1))

        return entries
