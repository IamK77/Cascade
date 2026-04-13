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

"""Context propagation logic for information flow through the Cascade."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING

from cascade.types import Context, ContextLevel

if TYPE_CHECKING:
    from cascade.core.cascade import Cascade


@dataclass
class PropagationResult:
    """Result of a context propagation operation."""

    reached_nodes: dict[str, Context]
    """Mapping of node IDs to the context they received."""

    distances: dict[str, int]
    """Distance from source to each reached node."""

    def __len__(self) -> int:
        return len(self.reached_nodes)

    def get_nodes_at_distance(self, distance: int) -> list[str]:
        """Get node IDs at a specific distance."""
        return [nid for nid, dist in self.distances.items() if dist == distance]


class ContextPropagator:
    """Handles context propagation through the Cascade."""

    def __init__(self, cascade: Cascade):
        self._cascade = cascade

    def propagate_from(
        self,
        source_id: str,
        context: Context,
        max_distance: int | None = None,
    ) -> PropagationResult:
        """Propagate context from a source node to its descendants."""
        if source_id not in self._cascade.nodes:
            raise ValueError(f"Source node {source_id} not found")

        result_contexts: dict[str, Context] = {}
        distances: dict[str, int] = {}
        visited: dict[str, int] = {source_id: 0}
        queue = deque([(source_id, 0)])

        while queue:
            current_id, distance = queue.popleft()
            if max_distance is not None and distance > max_distance:
                continue

            result_contexts[current_id] = context
            distances[current_id] = distance

            for dependent in self._cascade.get_dependents(current_id):
                if dependent.id not in visited:
                    visited[dependent.id] = distance + 1
                    queue.append((dependent.id, distance + 1))

        return PropagationResult(reached_nodes=result_contexts, distances=distances)

    def propagate_to_ancestors(
        self,
        target_id: str,
        context: Context,
        max_distance: int | None = None,
    ) -> PropagationResult:
        """Propagate context from a target node to its ancestors."""
        if target_id not in self._cascade.nodes:
            raise ValueError(f"Target node {target_id} not found")

        result_contexts: dict[str, Context] = {}
        distances: dict[str, int] = {}
        visited: dict[str, int] = {target_id: 0}
        queue = deque([(target_id, 0)])

        while queue:
            current_id, distance = queue.popleft()
            if max_distance is not None and distance > max_distance:
                continue

            result_contexts[current_id] = context
            distances[current_id] = distance

            for dependency in self._cascade.get_dependencies(current_id):
                if dependency.id not in visited:
                    visited[dependency.id] = distance + 1
                    queue.append((dependency.id, distance + 1))

        return PropagationResult(reached_nodes=result_contexts, distances=distances)

    def collect_context_at(self, node_id: str, max_distance: int = 2) -> Context:
        """Collect propagated context from ancestors at a node."""
        if node_id not in self._cascade.nodes:
            raise ValueError(f"Node {node_id} not found")

        visited: dict[str, int] = {node_id: 0}
        queue = deque([(node_id, 0)])
        collected = Context()

        while queue:
            current_id, distance = queue.popleft()
            if distance > max_distance:
                continue

            node = self._cascade.nodes[current_id]
            if node.context:
                for level in (ContextLevel.CRITICAL, ContextLevel.SUMMARY, ContextLevel.ARTIFACTS):
                    if node.context.propagate_to(level, distance):
                        if level == ContextLevel.CRITICAL:
                            collected.critical.update(node.context.critical)
                        elif level == ContextLevel.SUMMARY and distance <= 2:
                            if node.context.summary:
                                if collected.summary:
                                    collected.summary += "\n" + node.context.summary
                                else:
                                    collected.summary = node.context.summary
                        elif level == ContextLevel.ARTIFACTS:
                            if node.context.artifacts:
                                if collected.artifacts:
                                    collected.artifacts += "," + node.context.artifacts
                                else:
                                    collected.artifacts = node.context.artifacts

            if distance < max_distance:
                for dependency in self._cascade.get_dependencies(current_id):
                    if dependency.id not in visited:
                        visited[dependency.id] = distance + 1
                        queue.append((dependency.id, distance + 1))

        return collected

    def merge_contexts(self, contexts: list[Context]) -> Context:
        """Merge multiple contexts into one."""
        if not contexts:
            return Context()
        result = Context()
        for ctx in contexts:
            result = result.merge(ctx)
        return result
