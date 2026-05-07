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

"""Cascade core implementation — a task flow graph.

Design invariants:
    - Every edge carries exactly one Contract (frozen, never None).
    - Edge keys are (from_id, to_id) tuples, not string encodings.
    - Node dependency count is computed from the graph, never stored.
    - PENDING/READY transitions are managed centrally by Cascade.
    - Contract storage is encapsulated — use get_contract() for reads.
"""

import warnings
from collections import deque
from dataclasses import dataclass, field
from graphlib import CycleError as GraphlibCycleError
from graphlib import TopologicalSorter

from cascade.core.node import Node
from cascade.core.state import NodeState
from cascade.errors import ContractError, CycleError, NodeExistsError, NodeNotFoundError
from cascade.types import Contract, DependencyInfo, EdgeId, PromiseEntry


@dataclass
class Cascade:
    """Task flow graph for cascade-style scheduling.

    Public fields:
        nodes — node lookup by ID (read/write for state mutations).

    Internal fields (use methods instead of direct access):
        _adjacency — forward edges: who depends on me.
        _reverse   — backward edges: who I depend on.
        _contracts — edge contracts indexed by (from_id, to_id).
    """

    nodes: dict[str, Node] = field(default_factory=dict)
    epoch: int = 0
    _adjacency: dict[str, set[str]] = field(default_factory=dict, repr=False)
    _reverse: dict[str, set[str]] = field(default_factory=dict, repr=False)
    _contracts: dict[EdgeId, Contract] = field(default_factory=dict, repr=False)

    # ------------------------------------------------------------------
    # Epoch — monotonic version counter for fencing
    # ------------------------------------------------------------------

    def increment_epoch(self) -> int:
        """Advance epoch by 1 and return the new value."""
        self.epoch += 1
        return self.epoch

    # ------------------------------------------------------------------
    # Computed properties — no redundant state
    # ------------------------------------------------------------------

    def pending_dependency_count(self, node_id: str) -> int:
        """Count dependencies that are not yet COMPLETED.

        This replaces the old in_degree field. Always consistent because
        it is computed, not cached.
        """
        count = 0
        for dep_id in self._reverse.get(node_id, set()):
            dep_node = self.nodes.get(dep_id)
            if dep_node and dep_node.state != NodeState.COMPLETED:
                count += 1
        return count

    # ------------------------------------------------------------------
    # Agent tracking
    # ------------------------------------------------------------------

    def find_agent_active_task(self, agent_id: str) -> Node | None:
        """Find the ACTIVE task for a given agent."""
        for node in self.nodes.values():
            if node.agent_id == agent_id and node.state == NodeState.ACTIVE:
                return node
        return None

    # ------------------------------------------------------------------
    # Node operations
    # ------------------------------------------------------------------

    def add_node(self, node: Node) -> None:
        """Add a node to the graph, normalizing its initial state.

        If the node's state is PENDING or READY, it is recomputed from
        the graph (which at add-time has no edges to this node, so the
        result is READY). Terminal and ACTIVE states are preserved as-is.
        """
        if node.id in self.nodes:
            raise NodeExistsError(f"Node {node.id} already exists")
        self.nodes[node.id] = node
        self._adjacency[node.id] = set()
        self._reverse[node.id] = set()
        # Normalize: a node with no edges is READY, not PENDING.
        self._update_readiness(node.id)

    def remove_node(self, node_id: str) -> None:
        """Remove a node and all its edges from the graph."""
        if node_id not in self.nodes:
            raise NodeNotFoundError(f"Node {node_id} not found")

        for dep_id in list(self._reverse[node_id]):
            self.remove_edge(dep_id, node_id)
        for dependent_id in list(self._adjacency[node_id]):
            self.remove_edge(node_id, dependent_id)

        del self.nodes[node_id]
        del self._adjacency[node_id]
        del self._reverse[node_id]

    # ------------------------------------------------------------------
    # Edge operations
    # ------------------------------------------------------------------

    def add_edge(
        self,
        from_id: str,
        to_id: str,
        *,
        contract: Contract | None = None,
        expectation: str = "",
        promise: str = "",
        _skip_duplicate_warn: bool = False,
    ) -> None:
        """Add a directed edge from from_id to to_id.

        to_id depends on from_id (data flows from_id -> to_id).
        Accepts either a Contract object or separate expectation/promise strings.

        Raises:
            ValueError: If contract incomplete, nodes missing, or cycle would form.
        """
        if contract is not None:
            edge_contract = contract
        else:
            edge_contract = Contract(expectation=expectation, promise=promise)

        if not edge_contract.expectation or not edge_contract.expectation.strip():
            raise ContractError(f"expectation is required for edge {from_id} -> {to_id}")
        if not edge_contract.promise or not edge_contract.promise.strip():
            raise ContractError(f"promise is required for edge {from_id} -> {to_id}")
        if from_id not in self.nodes or to_id not in self.nodes:
            raise NodeNotFoundError(f"Both nodes must exist: {from_id}, {to_id}")

        edge_key: EdgeId = (from_id, to_id)

        # Update existing edge contract
        if to_id in self._adjacency[from_id]:
            self._contracts[edge_key] = edge_contract
            return

        if self._would_create_cycle(from_id, to_id):
            raise CycleError(f"Adding edge {from_id} -> {to_id} would create a cycle")

        self._adjacency[from_id].add(to_id)
        self._reverse[to_id].add(from_id)
        self._contracts[edge_key] = edge_contract
        self._update_readiness(to_id)

        if not _skip_duplicate_warn:
            existing_promises = [
                self._contracts[(dep_id, to_id)].promise
                for dep_id in self._reverse[to_id]
                if dep_id != from_id and (dep_id, to_id) in self._contracts
            ]
            if edge_contract.promise in existing_promises:
                warnings.warn(
                    f"Duplicate promise on edges to '{to_id}': \"{edge_contract.promise}\". "
                    f"Promise should describe what the upstream node delivers, not what the downstream produces.",
                    stacklevel=2,
                )

    def remove_edge(self, from_id: str, to_id: str) -> None:
        """Remove a directed edge and recompute readiness."""
        if to_id in self._adjacency.get(from_id, set()):
            self._adjacency[from_id].discard(to_id)
            self._reverse[to_id].discard(from_id)
            self._contracts.pop((from_id, to_id), None)
            self._update_readiness(to_id)

    def _restore_edge(self, from_id: str, to_id: str, contract: Contract) -> None:
        """Restore an edge during deserialization.

        Skips cycle detection (the saved graph is assumed acyclic) but
        DOES recompute readiness, so PENDING/READY states are always
        derived from the graph structure rather than trusted from storage.
        """
        self._adjacency[from_id].add(to_id)
        self._reverse[to_id].add(from_id)
        self._contracts[(from_id, to_id)] = contract
        self._update_readiness(to_id)

    # ------------------------------------------------------------------
    # Contract access (encapsulated — _contracts is not public)
    # ------------------------------------------------------------------

    def get_contract(self, from_id: str, to_id: str) -> Contract | None:
        """Get the contract for an edge, or None if the edge doesn't exist."""
        return self._contracts.get((from_id, to_id))

    def get_edge_metadata(self, from_id: str, to_id: str) -> dict[str, str | None]:
        """Get metadata for an edge as a dict (backward-compatible).

        Prefer get_contract() for new code.
        """
        contract = self._contracts.get((from_id, to_id))
        if contract:
            return {"expectation": contract.expectation, "promise": contract.promise}
        return {"expectation": None, "promise": None}

    # ------------------------------------------------------------------
    # Readiness management — centralized
    # ------------------------------------------------------------------

    def _update_readiness(self, node_id: str) -> None:
        """Recompute PENDING/READY state for a node.

        Only touches non-terminal, non-ACTIVE nodes — explicit states
        are never overwritten.
        """
        node = self.nodes.get(node_id)
        if node is None:
            return
        if node.state in (
            NodeState.ACTIVE,
            NodeState.COMPLETED,
            NodeState.FAILED,
            NodeState.CANCELLED,
        ):
            return

        pending = self.pending_dependency_count(node_id)
        if pending == 0 and node.state == NodeState.PENDING:
            node.state = NodeState.READY
        elif pending > 0 and node.state == NodeState.READY:
            node.state = NodeState.PENDING

    def notify_completion(self, node_id: str) -> list[str]:
        """Called when a node completes — recompute readiness of dependents.

        Returns list of node IDs that became READY.
        """
        unblocked: list[str] = []
        for dependent_id in self._adjacency.get(node_id, set()):
            dependent = self.nodes.get(dependent_id)
            if dependent is None:
                continue
            old_state = dependent.state
            self._update_readiness(dependent_id)
            if old_state == NodeState.PENDING and dependent.state == NodeState.READY:
                unblocked.append(dependent_id)
        return unblocked

    # ------------------------------------------------------------------
    # Query methods
    # ------------------------------------------------------------------

    def get_ready_nodes(self, prioritize: bool = True) -> list[Node]:
        """Get all nodes ready to execute.

        If prioritize=True (default), nodes are sorted by downstream depth
        descending — nodes that unblock the most downstream work come first.
        This is critical-path scheduling.
        """
        ready = [n for n in self.nodes.values() if n.state == NodeState.READY]
        if prioritize and len(ready) > 1:
            depths = self._compute_downstream_depths()
            ready.sort(key=lambda n: depths.get(n.id, 0), reverse=True)
        return ready

    def _compute_downstream_depths(self) -> dict[str, int]:
        """Compute downstream depth for each node via topological-order DP.

        downstream_depth(n) = 0 if n is a leaf,
                            = 1 + max(downstream_depth(child) for child in dependents(n))
                              counting only non-terminal children.

        Nodes with higher depth are on longer (more critical) paths.
        """
        depths: dict[str, int] = {}

        # Process in reverse topological order (leaves first)
        topo = self.topological_sort()

        for node_id in reversed(topo):
            max_child_depth = -1
            for dep_id in self._adjacency.get(node_id, set()):
                dep_node = self.nodes.get(dep_id)
                if dep_node and not dep_node.state.is_terminal():
                    child_depth = depths.get(dep_id, 0)
                    if child_depth > max_child_depth:
                        max_child_depth = child_depth
            depths[node_id] = 0 if max_child_depth == -1 else max_child_depth + 1

        return depths

    def get_critical_path(self) -> list[str]:
        """Get the critical path — the longest chain of uncompleted nodes.

        Returns node IDs from root to leaf along the longest path.
        Useful for visualization and scheduling insight.
        """
        depths = self._compute_downstream_depths()
        if not depths:
            return []

        # Start from the non-terminal node with highest depth
        candidates = [nid for nid in depths if not self.nodes[nid].state.is_terminal()]
        if not candidates:
            return []

        path: list[str] = []
        current: str | None = max(candidates, key=lambda nid: depths[nid])

        while current:
            path.append(current)
            # Follow the child with highest depth
            best_child: str | None = None
            best_depth = -1
            for dep_id in self._adjacency.get(current, set()):
                dep_node = self.nodes.get(dep_id)
                if dep_node and not dep_node.state.is_terminal():
                    d = depths.get(dep_id, 0)
                    if d > best_depth:
                        best_depth = d
                        best_child = dep_id
            current = best_child

        return path

    def get_node_dependencies_info(self, node_id: str) -> list[DependencyInfo]:
        """Get dependency information for a node, including contracts."""
        result: list[DependencyInfo] = []
        for dep_id in self._reverse.get(node_id, set()):
            contract = self.get_contract(dep_id, node_id)
            result.append(
                DependencyInfo(
                    node_id=dep_id,
                    expectation=contract.expectation if contract else None,
                    promise=contract.promise if contract else None,
                )
            )
        return result

    def get_node_promises(self, node_id: str) -> list[PromiseEntry]:
        """Get all promises this node has made to its dependents."""
        result: list[PromiseEntry] = []
        for dependent_id in self._adjacency.get(node_id, set()):
            contract = self.get_contract(node_id, dependent_id)
            if contract:
                result.append(
                    PromiseEntry(
                        to_node=dependent_id,
                        expectation=contract.expectation,
                        promise=contract.promise,
                    )
                )
        return result

    def has_dependency(self, node_id: str, dep_id: str) -> bool:
        """Check if node_id depends on dep_id."""
        return dep_id in self._reverse.get(node_id, set())

    def get_dependencies(self, node_id: str) -> list[Node]:
        """Get all nodes that this node depends on."""
        return [
            self.nodes[dep_id]
            for dep_id in self._reverse.get(node_id, set())
            if dep_id in self.nodes
        ]

    def get_dependents(self, node_id: str) -> list[Node]:
        """Get all nodes that depend on this node."""
        return [
            self.nodes[dep_id]
            for dep_id in self._adjacency.get(node_id, set())
            if dep_id in self.nodes
        ]

    # ------------------------------------------------------------------
    # Topological sort & cycle detection
    # ------------------------------------------------------------------

    def topological_sort(self) -> list[str]:
        """Topological sort via graphlib.TopologicalSorter."""
        sorter = TopologicalSorter[str]()
        for nid in self.nodes:
            sorter.add(nid, *self._reverse[nid])
        try:
            return list(sorter.static_order())
        except GraphlibCycleError:
            raise CycleError("Graph contains a cycle")

    def _would_create_cycle(self, from_id: str, to_id: str) -> bool:
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
            stack.extend(self._adjacency.get(current, set()))
        return False

    def has_cycle(self) -> bool:
        try:
            self.topological_sort()
            return False
        except CycleError:
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
            for neighbor in self._adjacency.get(node_id, set()):
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

    # ------------------------------------------------------------------
    # Connectivity
    # ------------------------------------------------------------------

    def is_connected(self) -> bool:
        """Check if the graph is a single connected component (undirected)."""
        if not self.nodes:
            return True

        start_node = next(iter(self.nodes.keys()))
        visited: set[str] = {start_node}
        queue = deque([start_node])

        while queue:
            current = queue.popleft()
            for dep_id in self._reverse.get(current, set()):
                if dep_id not in visited:
                    visited.add(dep_id)
                    queue.append(dep_id)
            for dependent_id in self._adjacency.get(current, set()):
                if dependent_id not in visited:
                    visited.add(dependent_id)
                    queue.append(dependent_id)

        return len(visited) == len(self.nodes)

    # ------------------------------------------------------------------
    # Dunder
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self.nodes)

    def __repr__(self) -> str:
        return f"Cascade(nodes={len(self.nodes)}, edges={self._edge_count()})"

    def _edge_count(self) -> int:
        return sum(len(edges) for edges in self._adjacency.values())
