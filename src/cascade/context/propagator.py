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

from collections import deque
from dataclasses import dataclass

from cascade.core.cascade import Cascade
from cascade.protocols.context_protocol import (
    ContextLevel,
    ContextProtocol,
)


@dataclass
class PropagationResult:
    """Result of a context propagation operation."""

    reached_nodes: dict[str, ContextProtocol]
    """Mapping of node IDs to the context they received."""

    distances: dict[str, int]
    """Distance from source to each reached node."""

    def __len__(self) -> int:
        return len(self.reached_nodes)

    def get_nodes_at_distance(self, distance: int) -> list[str]:
        """Get node IDs at a specific distance.

        Args:
            distance: Distance to filter by

        Returns:
            List of node IDs at this distance
        """
        return [nid for nid, dist in self.distances.items() if dist == distance]


class ContextPropagator:
    """Handles context propagation through the Cascade.

    Context propagates along dependency edges with different rules
    for each context level.
    """

    def __init__(self, cascade: Cascade):
        """Create a context propagator for a Cascade.

        Args:
            cascade: The Cascade to propagate context through
        """
        self._cascade = cascade

    def propagate_from(
        self,
        source_id: str,
        context: ContextProtocol,
        max_distance: int | None = None,
    ) -> PropagationResult:
        """Propagate context from a source node to its descendants.

        Args:
            source_id: ID of the source node
            context: Context to propagate
            max_distance: Maximum distance to propagate (None = unlimited)

        Returns:
            PropagationResult containing reached nodes and distances
        """
        if source_id not in self._cascade.nodes:
            raise ValueError(f"Source node {source_id} not found")

        result_contexts: dict[str, ContextProtocol] = {}
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
        context: ContextProtocol,
        max_distance: int | None = None,
    ) -> PropagationResult:
        """Propagate context from a target node to its ancestors.

        Args:
            target_id: ID of the target node
            context: Context to propagate
            max_distance: Maximum distance to propagate (None = unlimited)

        Returns:
            PropagationResult containing reached nodes and distances
        """
        if target_id not in self._cascade.nodes:
            raise ValueError(f"Target node {target_id} not found")

        result_contexts: dict[str, ContextProtocol] = {}
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

    def collect_context_at(self, node_id: str, max_distance: int = 2) -> ContextProtocol:
        """Collect propagated context from ancestors at a node.

        Args:
            node_id: ID of the node to collect context at
            max_distance: Maximum distance to look back

        Returns:
            Merged context from all reachable ancestors
        """
        from cascade.context.context import Context

        if node_id not in self._cascade.nodes:
            raise ValueError(f"Node {node_id} not found")

        visited: dict[str, int] = {node_id: 0}
        queue = deque([(node_id, 0)])
        collected_context = Context()

        while queue:
            current_id, distance = queue.popleft()

            if distance > max_distance:
                continue

            node = self._cascade.nodes[current_id]
            if node.context:
                for level in (ContextLevel.CRITICAL, ContextLevel.SUMMARY, ContextLevel.ARTIFACTS):
                    if node.context.propagate_to(level, distance):
                        if level == ContextLevel.CRITICAL:
                            collected_context.critical.update(node.context.critical)
                        elif level == ContextLevel.SUMMARY and distance <= 2:
                            if node.context.summary:
                                if collected_context.summary:
                                    collected_context.summary += "\n" + node.context.summary
                                else:
                                    collected_context.summary = node.context.summary
                        elif level == ContextLevel.ARTIFACTS:
                            if node.context.artifacts:
                                if collected_context.artifacts:
                                    collected_context.artifacts += "," + node.context.artifacts
                                else:
                                    collected_context.artifacts = node.context.artifacts

            if distance < max_distance:
                for dependency in self._cascade.get_dependencies(current_id):
                    if dependency.id not in visited:
                        visited[dependency.id] = distance + 1
                        queue.append((dependency.id, distance + 1))

        return collected_context

    def merge_contexts(self, contexts: list[ContextProtocol]) -> ContextProtocol:
        """Merge multiple contexts.

        Args:
            contexts: List of contexts to merge

        Returns:
            Merged context
        """
        from cascade.context.context import Context

        if not contexts:
            return Context()

        result = Context()
        for ctx in contexts:
            result = result.merge(ctx)

        return result
