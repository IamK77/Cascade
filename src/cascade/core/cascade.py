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

"""Cascade core implementation - a task flow graph."""

from collections import deque
from dataclasses import dataclass, field
from typing import Any

from cascade.core.state import NodeState
from cascade.protocols.node_protocol import NodeProtocol


@dataclass
class Cascade:
    """Task flow graph for cascade-style scheduling.

    The Cascade maintains:
    - All nodes indexed by ID
    - Forward adjacency: node_id -> {dependent_ids} (who depends on me)
    - Reverse adjacency: node_id -> {dependency_ids} (who I depend on)
    - Edge metadata: "from_id->to_id" -> {expectation, promise}

    Edge direction: from_id -> to_id means to_id depends on from_id
    (data/control flows from from_id to to_id)

    Contract information (expectation/promise) is stored on edges, not on nodes.
    This allows a node to have different promises to different downstream nodes.
    """

    nodes: dict[str, NodeProtocol] = field(default_factory=dict)
    adjacency_list: dict[str, set[str]] = field(default_factory=dict)
    reverse_adjacency: dict[str, set[str]] = field(default_factory=dict)
    edge_metadata: dict[str, dict[str, str | None]] = field(default_factory=dict)

    def find_agent_active_task(self, agent_id: str) -> NodeProtocol | None:
        """Find the ACTIVE task for a given agent."""
        for node in self.nodes.values():
            if node.agent_id == agent_id and node.state == NodeState.ACTIVE:
                return node
        return None

    def add_node(self, node: NodeProtocol) -> None:
        """Add a node to the graph."""
        if node.id in self.nodes:
            raise ValueError(f"Node {node.id} already exists")
        self.nodes[node.id] = node
        self.adjacency_list[node.id] = set()
        self.reverse_adjacency[node.id] = set()

    def remove_node(self, node_id: str) -> None:
        """Remove a node from the graph."""
        if node_id not in self.nodes:
            raise ValueError(f"Node {node_id} not found")

        # Remove all incoming edges
        for dep_id in list(self.reverse_adjacency[node_id]):
            self.remove_edge(dep_id, node_id)

        # Remove all outgoing edges
        for dependent_id in list(self.adjacency_list[node_id]):
            self.remove_edge(node_id, dependent_id)

        # Remove node
        del self.nodes[node_id]
        del self.adjacency_list[node_id]
        del self.reverse_adjacency[node_id]

    def add_edge(
        self,
        from_id: str,
        to_id: str,
        expectation: str | None = None,
        promise: str | None = None,
    ) -> None:
        """Add a directed edge from from_id to to_id.

        This means to_id depends on from_id (data flows from_id -> to_id).

        Args:
            from_id: Source node ID (the dependency)
            to_id: Target node ID (the dependent)
            expectation: What to_id expects from from_id (optional)
            promise: What from_id promises to provide to to_id (optional)
        """
        if from_id not in self.nodes or to_id not in self.nodes:
            raise ValueError(f"Both nodes must exist: {from_id}, {to_id}")

        # Check if edge already exists
        if to_id in self.adjacency_list[from_id]:
            # Update metadata even if edge exists
            edge_key = f"{from_id}->{to_id}"
            if expectation is not None or promise is not None:
                if edge_key not in self.edge_metadata:
                    self.edge_metadata[edge_key] = {}
                if expectation is not None:
                    self.edge_metadata[edge_key]["expectation"] = expectation
                if promise is not None:
                    self.edge_metadata[edge_key]["promise"] = promise
            return

        # Cycle detection
        if self._would_create_cycle(from_id, to_id):
            raise ValueError(f"Adding edge {from_id} -> {to_id} would create a cycle")

        self.adjacency_list[from_id].add(to_id)
        self.reverse_adjacency[to_id].add(from_id)

        # Store edge metadata
        edge_key = f"{from_id}->{to_id}"
        self.edge_metadata[edge_key] = {"expectation": expectation, "promise": promise}

        # Update in-degree
        target_node = self.nodes[to_id]
        if hasattr(target_node, "increment_in_degree"):
            target_node.increment_in_degree()

    def remove_edge(self, from_id: str, to_id: str) -> None:
        """Remove a directed edge."""
        if to_id in self.adjacency_list.get(from_id, set()):
            self.adjacency_list[from_id].discard(to_id)
            self.reverse_adjacency[to_id].discard(from_id)

            # Remove edge metadata
            edge_key = f"{from_id}->{to_id}"
            self.edge_metadata.pop(edge_key, None)

            # Update in-degree
            target_node = self.nodes[to_id]
            if hasattr(target_node, "decrement_in_degree"):
                target_node.decrement_in_degree()

    def get_ready_nodes(self) -> list[NodeProtocol]:
        """Get all nodes ready to execute (in_degree == 0 and state == READY)."""
        return [
            node
            for node in self.nodes.values()
            if node.in_degree == 0 and node.state == NodeState.READY
        ]

    def get_edge_metadata(self, from_id: str, to_id: str) -> dict[str, str | None]:
        """Get metadata for an edge.

        Returns dict with 'expectation' and 'promise' (may be None).
        """
        edge_key = f"{from_id}->{to_id}"
        return self.edge_metadata.get(edge_key, {"expectation": None, "promise": None})

    def get_node_dependencies_info(self, node_id: str) -> list[dict[str, Any]]:
        """Get dependency information for a node.

        Returns list of dicts with:
        - node_id: the dependency node's ID
        - expectation: what this node expects from the dependency
        - promise: what the dependency promises to provide
        """
        result = []
        for dep_id in self.reverse_adjacency.get(node_id, set()):
            metadata = self.get_edge_metadata(dep_id, node_id)
            result.append({
                "node_id": dep_id,
                "expectation": metadata.get("expectation"),
                "promise": metadata.get("promise"),
            })
        return result

    def get_node_promises(self, node_id: str) -> list[dict[str, Any]]:
        """Get all promises this node has made to its dependents.

        Returns list of dicts with:
        - to_node: the dependent node's ID
        - promise: what this node promises to provide
        """
        result = []
        for dependent_id in self.adjacency_list.get(node_id, set()):
            metadata = self.get_edge_metadata(node_id, dependent_id)
            if metadata.get("promise"):
                result.append({
                    "to_node": dependent_id,
                    "promise": metadata["promise"],
                })
        return result

    def _get_visible_descendants(self, node_id: str, max_distance: int = 2) -> dict[str, Any]:
        """Get visible descendant nodes within specified distance."""
        result: dict[str, Any] = {}
        visited: dict[str, int] = {node_id: 0}
        queue = deque([(node_id, 0)])

        while queue:
            current_id, distance = queue.popleft()

            if distance < max_distance:
                for dependent in self.get_dependents(current_id):
                    if dependent.id not in visited:
                        visited[dependent.id] = distance + 1
                        queue.append((dependent.id, distance + 1))

            if distance == 0 or distance > max_distance:
                continue

            current_node = self.nodes[current_id]
            node_info: dict[str, Any] = {
                "id": current_node.id,
                "state": current_node.state.name,
            }

            # Add this node's expectations from its dependencies
            expectations = []
            for dep_info in self.get_node_dependencies_info(current_id):
                expect_info: dict[str, Any] = {"node_id": dep_info["node_id"]}
                if dep_info["expectation"]:
                    expect_info["expectation"] = dep_info["expectation"]
                if dep_info["promise"]:
                    expect_info["promise"] = dep_info["promise"]
                expectations.append(expect_info)

            if expectations:
                node_info["expectations"] = expectations

            distance_key = str(distance)
            if distance_key not in result:
                result[distance_key] = []
            result[distance_key].append(node_info)

        return result

    def get_node_view(self, node_id: str) -> dict[str, Any]:
        """Get all information an agent needs to execute a node."""
        if node_id not in self.nodes:
            raise ValueError(f"Node {node_id} not found")

        node = self.nodes[node_id]

        # Get merged context from upstream
        from cascade.context.propagator import ContextPropagator

        propagator = ContextPropagator(self)
        merged_context = propagator.collect_context_at(node_id)

        # Build context dict
        context_dict: dict[str, Any] = {}
        if merged_context.critical:
            context_dict["critical"] = merged_context.critical
        if merged_context.summary:
            context_dict["summary"] = merged_context.summary
        if merged_context.artifacts:
            context_dict["artifacts"] = merged_context.artifacts

        # Build contracts list (from edge metadata)
        contracts = []
        for dep_info in self.get_node_dependencies_info(node_id):
            contract_dict: dict[str, Any] = {"node_id": dep_info["node_id"]}
            if dep_info["expectation"]:
                contract_dict["expectation"] = dep_info["expectation"]
            if dep_info["promise"]:
                contract_dict["promise"] = dep_info["promise"]
            contracts.append(contract_dict)

        # Get promises this node should fulfill
        promises = self.get_node_promises(node_id)

        # Get visible descendant nodes
        visible_descendants = self._get_visible_descendants(node_id, max_distance=2)

        # Build result
        result: dict[str, Any] = {
            "id": node.id,
            "state": node.state.name,
        }

        if context_dict:
            result["context"] = context_dict

        if contracts:
            result["contracts"] = contracts

        if promises:
            result["promises"] = promises

        if visible_descendants:
            result["visible_nodes"] = visible_descendants

        return result

    def get_dependencies(self, node_id: str) -> list[NodeProtocol]:
        """Get all nodes that this node depends on."""
        return [
            self.nodes[dep_id]
            for dep_id in self.reverse_adjacency.get(node_id, set())
            if dep_id in self.nodes
        ]

    def get_dependents(self, node_id: str) -> list[NodeProtocol]:
        """Get all nodes that depend on this node."""
        return [
            self.nodes[dep_id]
            for dep_id in self.adjacency_list.get(node_id, set())
            if dep_id in self.nodes
        ]

    def topological_sort(self) -> list[str]:
        """Perform topological sort using Kahn's algorithm."""
        in_degree = {node_id: len(self.reverse_adjacency[node_id]) for node_id in self.nodes}
        queue = deque([node_id for node_id, degree in in_degree.items() if degree == 0])
        result = []

        while queue:
            node_id = queue.popleft()
            result.append(node_id)

            for dependent in self.adjacency_list[node_id]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        if len(result) != len(self.nodes):
            raise ValueError("Graph contains a cycle")

        return result

    def _would_create_cycle(self, from_id: str, to_id: str) -> bool:
        """Check if adding edge would create a cycle."""
        return self._has_path(to_id, from_id)

    def _has_path(self, from_id: str, to_id: str) -> bool:
        """Check if there's a path from from_id to to_id using DFS."""
        visited: set[str] = set()
        stack = [from_id]

        while stack:
            current = stack.pop()
            if current == to_id:
                return True
            if current in visited:
                continue
            visited.add(current)
            stack.extend(self.adjacency_list.get(current, set()))

        return False

    def has_cycle(self) -> bool:
        """Check if the graph contains a cycle."""
        try:
            self.topological_sort()
            return False
        except ValueError:
            return True

    def find_cycle(self) -> list[str] | None:
        """Find a cycle in the graph using DFS."""
        visited: set[str] = set()
        rec_stack: set[str] = set()
        path: list[str] = []

        def dfs(node_id: str) -> list[str] | None:
            visited.add(node_id)
            rec_stack.add(node_id)
            path.append(node_id)

            for neighbor in self.adjacency_list.get(node_id, set()):
                if neighbor not in visited:
                    result = dfs(neighbor)
                    if result:
                        return result
                elif neighbor in rec_stack:
                    cycle_start = path.index(neighbor)
                    return path[cycle_start:] + [neighbor]

            path.pop()
            rec_stack.remove(node_id)
            return None

        for node_id in self.nodes:
            if node_id not in visited:
                result = dfs(node_id)
                if result:
                    return result

        return None

    def __len__(self) -> int:
        """Get number of nodes in the graph."""
        return len(self.nodes)

    def __repr__(self) -> str:
        return f"Cascade(nodes={len(self.nodes)}, edges={self._edge_count()})"

    def _edge_count(self) -> int:
        """Count total edges."""
        return sum(len(edges) for edges in self.adjacency_list.values())

    def is_connected(self) -> bool:
        """Check if the graph is a single connected component.

        Uses BFS to verify all nodes are reachable from any starting node
        (treating edges as undirected for connectivity check).

        Returns:
            True if graph is connected or empty, False if there are multiple components.
        """
        if not self.nodes:
            return True

        # Start from any node
        start_node = next(iter(self.nodes.keys()))
        visited: set[str] = {start_node}
        queue = [start_node]

        while queue:
            current = queue.pop(0)

            # Check all neighbors (both upstream and downstream)
            # Upstream: nodes this node depends on
            for dep_id in self.reverse_adjacency.get(current, set()):
                if dep_id not in visited:
                    visited.add(dep_id)
                    queue.append(dep_id)

            # Downstream: nodes that depend on this node
            for dependent_id in self.adjacency_list.get(current, set()):
                if dependent_id not in visited:
                    visited.add(dependent_id)
                    queue.append(dependent_id)

        # Graph is connected if we visited all nodes
        return len(visited) == len(self.nodes)
