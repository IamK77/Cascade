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

"""Client mixin — DAG structure operations (add, remove, split, refine, edit)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from cascade import tips
from cascade.client.base import _update_context
from cascade.core.cascade import Cascade
from cascade.core.node import Node
from cascade.core.state import NodeState
from cascade.events import EventType
from cascade.operations.remove import RemoveOperation
from cascade.operations.split import SplitOperation
from cascade.types import Contract, ErrorCode, Result

if TYPE_CHECKING:
    from cascade.client.base import ClientBase


class StructureMixin:
    """DAG structure operations: add, add_batch, remove, split, refine, edit."""

    def add(
        self: ClientBase,
        node_id: str,
        *,
        deps: dict[str, Contract] | None = None,
        dependents: dict[str, Contract] | None = None,
        op_id: str | None = None,
    ) -> Result:
        """Add a task node to the DAG.

        Args:
            node_id: Unique task identifier.
            deps: Dependencies with contracts.
            dependents: Dependents with contracts.
            op_id: Idempotency key.
        """
        cached = self._cached_op(op_id)
        if cached is not None:
            return cached
        try:
            with self._mutate(op_id) as tx:
                r = self._add_locked(tx.graph, node_id, deps, dependents)
                if not r.success:
                    return r
                tx.emit(
                    EventType.NODE_ADDED,
                    node_id=node_id,
                    dependencies=list(deps.keys()) if deps else [],
                    dependents=list(dependents.keys()) if dependents else [],
                    deps_contracts=[
                        {"node_id": k, "expectation": v.expectation, "promise": v.promise}
                        for k, v in (deps or {}).items()
                    ],
                    dependent_contracts=[
                        {"node_id": k, "expectation": v.expectation, "promise": v.promise}
                        for k, v in (dependents or {}).items()
                    ],
                )
                return tx.ok(r)
        except Exception as e:
            return Result(
                success=False, message=f"Operation failed: {e}", code=ErrorCode.INTERNAL_ERROR
            )

    def add_batch(
        self: ClientBase,
        specs: list[dict[str, Any]],
    ) -> Result:
        """Atomically add multiple nodes in one lock acquisition.

        Each spec is `{"node_id": str, "deps": dict[str, Contract] | None,
        "dependents": dict[str, Contract] | None}`. If any node fails,
        no nodes are added and no events emitted — the operation is atomic.
        """
        if not specs:
            return Result(success=True, message="No nodes to add", data={"added": []})

        try:
            with self._mutate() as tx:
                added: list[dict[str, Any]] = []

                for spec in specs:
                    nid = spec.get("node_id")
                    if not nid:
                        return Result(
                            success=False,
                            message=f"Batch failed: spec missing node_id ({spec})",
                            code=ErrorCode.BATCH_INVALID_SPEC,
                        )
                    r = self._add_locked(
                        tx.graph,
                        nid,
                        spec.get("deps"),
                        spec.get("dependents"),
                    )
                    if not r.success:
                        return Result(
                            success=False,
                            message=f"Batch failed at '{nid}': {r.message}",
                            code=ErrorCode.BATCH_INVALID_SPEC,
                        )
                    spec_deps = spec.get("deps") or {}
                    spec_dependents = spec.get("dependents") or {}
                    added.append(
                        {
                            "node_id": nid,
                            "deps": list(spec_deps.keys()),
                            "dependents": list(spec_dependents.keys()),
                            "deps_contracts": [
                                {"node_id": k, "expectation": v.expectation, "promise": v.promise}
                                for k, v in spec_deps.items()
                            ],
                            "dependent_contracts": [
                                {"node_id": k, "expectation": v.expectation, "promise": v.promise}
                                for k, v in spec_dependents.items()
                            ],
                        }
                    )

                for entry in added:
                    tx.emit(
                        EventType.NODE_ADDED,
                        node_id=entry["node_id"],
                        dependencies=entry["deps"],
                        dependents=entry["dependents"],
                        deps_contracts=entry.get("deps_contracts", []),
                        dependent_contracts=entry.get("dependent_contracts", []),
                    )
                tx.save()

                return Result(
                    success=True,
                    message=f"Added {len(added)} nodes",
                    data={"added": [a["node_id"] for a in added]},
                )
        except Exception as e:
            return Result(
                success=False, message=f"Operation failed: {e}", code=ErrorCode.INTERNAL_ERROR
            )

    def _add_locked(
        self: ClientBase,
        cascade: Cascade,
        node_id: str,
        deps: dict[str, Contract] | None,
        dependents: dict[str, Contract] | None,
    ) -> Result:
        """Single-node add on an already-loaded graph. Caller handles lock/save/emit."""
        dep_ids = list(deps.keys()) if deps else []
        dependent_ids = list(dependents.keys()) if dependents else []

        if node_id in cascade.nodes:
            return Result(
                success=False, message=f"Node {node_id} already exists", code=ErrorCode.NODE_EXISTS
            )

        for dep_id in dep_ids:
            if dep_id not in cascade.nodes:
                return Result(
                    success=False,
                    message=f"Dependency {dep_id} not found. Create it first.",
                    code=ErrorCode.DEP_NOT_FOUND,
                )
        for dep_id in dependent_ids:
            if dep_id not in cascade.nodes:
                return Result(
                    success=False,
                    message=f"Dependent {dep_id} not found. Create it first.",
                    code=ErrorCode.DEP_NOT_FOUND,
                )

        initial_state = NodeState.READY
        for dep_id in dep_ids:
            if dep_id in cascade.nodes and cascade.nodes[dep_id].state != NodeState.COMPLETED:
                initial_state = NodeState.PENDING
                break

        node = Node(id=node_id, state=initial_state)
        cascade.add_node(node)
        affected_nodes = [node_id]

        for dep_id in dep_ids:
            contract = deps[dep_id]  # type: ignore[index]
            cascade.add_edge(
                dep_id,
                node_id,
                expectation=contract.expectation,
                promise=contract.promise,
            )
            affected_nodes.append(dep_id)

        for dep_id in dependent_ids:
            contract = dependents[dep_id]  # type: ignore[index]
            cascade.add_edge(
                node_id,
                dep_id,
                expectation=contract.expectation,
                promise=contract.promise,
            )
            affected_nodes.append(dep_id)

        return Result(
            success=True,
            message=f"Node {node_id} added successfully",
            data={
                "node_id": node_id,
                "state": initial_state.name,
                "affected_nodes": list(set(affected_nodes)),
            },
        )

    def remove(
        self: ClientBase,
        node_id: str,
        *,
        cascade: bool = False,
        reason: str = "",
        op_id: str | None = None,
    ) -> Result:
        """Remove a node from the DAG."""
        cached = self._cached_op(op_id)
        if cached is not None:
            return cached
        try:
            with self._mutate(op_id) as tx:
                if node_id not in tx.graph.nodes:
                    return Result(
                        success=False,
                        message=f"Node {node_id} not found",
                        code=ErrorCode.TASK_NOT_FOUND,
                    )

                node = tx.graph.nodes[node_id]
                if node.state == NodeState.ACTIVE:
                    return Result(
                        success=False,
                        message=(
                            f"Cannot remove ACTIVE node {node_id} (agent: {node.agent_id}). "
                            f"Use finish_task with release=true first."
                        ),
                        data={"state": "ACTIVE", "agent_id": node.agent_id},
                        code=ErrorCode.TASK_ALREADY_ACTIVE,
                    )

                if cascade:
                    active_descendants = [
                        dep.id
                        for dep in tx.graph.get_dependents(node_id)
                        if dep.state == NodeState.ACTIVE
                    ]
                    if active_descendants:
                        return Result(
                            success=False,
                            message=(
                                f"Cannot cascade-remove: {active_descendants} are ACTIVE. "
                                f"Release them first."
                            ),
                            data={"active_nodes": active_descendants},
                            code=ErrorCode.TASK_ALREADY_ACTIVE,
                        )

                operation = RemoveOperation(tx.graph)
                result = operation.execute(node_id=node_id, cascade=cascade)

                if result.success:
                    tx.emit(
                        EventType.NODE_REMOVED,
                        node_id=node_id,
                        cascade=cascade,
                        affected_nodes=result.affected_nodes,
                        reason=reason,
                    )
                tx.save()
                return Result(
                    success=result.success,
                    message=result.message,
                    data={
                        "node_id": result.data.node_id if result.data else None,
                        "cascade": result.data.cascade if result.data else False,
                        "affected_nodes": result.affected_nodes,
                    },
                )

        except Exception as e:
            return Result(
                success=False, message=f"Operation failed: {e}", code=ErrorCode.INTERNAL_ERROR
            )

    def split(
        self: ClientBase,
        node_id: str,
        into: list[str],
        *,
        reason: str = "",
        op_id: str | None = None,
    ) -> Result:
        """Split a node into multiple subtasks."""
        if not into:
            return Result(
                success=False,
                message="new_nodes must be a non-empty list",
                code=ErrorCode.INVALID_INPUT,
            )
        cached = self._cached_op(op_id)
        if cached is not None:
            return cached

        try:
            with self._mutate(op_id) as tx:
                if node_id not in tx.graph.nodes:
                    return Result(
                        success=False,
                        message=f"Parent node {node_id} not found",
                        code=ErrorCode.TASK_NOT_FOUND,
                    )

                parent = tx.graph.nodes[node_id]
                if parent.state == NodeState.ACTIVE:
                    return Result(
                        success=False,
                        message=(
                            f"Cannot split ACTIVE node {node_id} (agent: {parent.agent_id}). "
                            f"Use finish_task with release=true first."
                        ),
                        data={"state": "ACTIVE", "agent_id": parent.agent_id},
                        code=ErrorCode.TASK_ALREADY_ACTIVE,
                    )

                parent_state = parent.state
                new_nodes = [Node(id=nid, state=parent_state) for nid in into]

                operation = SplitOperation(tx.graph)
                result = operation.execute(parent_id=node_id, new_nodes=new_nodes)

                if result.success:
                    tx.emit(
                        EventType.NODE_SPLIT,
                        node_id=node_id,
                        new_node_ids=result.data.new_node_ids if result.data else [],
                        reason=reason,
                    )
                tx.save()
                return Result(
                    success=result.success,
                    message=result.message,
                    data={
                        "parent_id": result.data.parent_id if result.data else None,
                        "new_node_ids": result.data.new_node_ids if result.data else [],
                        "affected_nodes": result.affected_nodes,
                    },
                )

        except Exception as e:
            return Result(
                success=False, message=f"Operation failed: {e}", code=ErrorCode.INTERNAL_ERROR
            )

    def refine(
        self: ClientBase,
        node_id: str,
        dep_id: str,
        expectation: str,
        promise: str,
        *,
        reason: str = "",
        op_id: str | None = None,
    ) -> Result:
        """Add a dependency to an existing node."""
        if not expectation or not expectation.strip():
            return Result(
                success=False,
                message="Missing required parameter: expectation",
                code=ErrorCode.INVALID_INPUT,
            )
        if not promise or not promise.strip():
            return Result(
                success=False,
                message="Missing required parameter: promise",
                code=ErrorCode.INVALID_INPUT,
            )
        cached = self._cached_op(op_id)
        if cached is not None:
            return cached

        try:
            with self._mutate(op_id) as tx:
                if node_id not in tx.graph.nodes:
                    return Result(
                        success=False,
                        message=f"Node {node_id} not found",
                        code=ErrorCode.TASK_NOT_FOUND,
                    )
                if dep_id not in tx.graph.nodes:
                    return Result(
                        success=False,
                        message=f"Dependency {dep_id} not found. Create it first with add_node.",
                        code=ErrorCode.DEP_NOT_FOUND,
                    )

                if tx.graph.has_dependency(node_id, dep_id):
                    return Result(
                        success=False,
                        message=f"Node {node_id} already depends on {dep_id}",
                        code=ErrorCode.INVALID_INPUT,
                    )

                if tx.graph._has_path(node_id, dep_id):
                    return Result(
                        success=False,
                        message=f"Adding dependency {dep_id} to {node_id} would create a cycle",
                        code=ErrorCode.INVALID_INPUT,
                    )

                old_state = tx.graph.nodes[node_id].state
                tx.graph.add_edge(dep_id, node_id, expectation=expectation, promise=promise)
                new_state = tx.graph.nodes[node_id].state

                refine_tips = tips.on_refine(
                    node_id=node_id,
                    dep_id=dep_id,
                    old_state=old_state.name,
                    new_state=new_state.name,
                )

                tx.emit(
                    EventType.NODE_REFINED,
                    node_id=node_id,
                    dependency_id=dep_id,
                    expectation=expectation,
                    promise=promise,
                    reason=reason,
                )
                return tx.ok(
                    Result(
                        success=True,
                        message=tips.append_tips(
                            f"Node {node_id} now depends on {dep_id}", refine_tips
                        ),
                        data={
                            "node_id": node_id,
                            "dependency_id": dep_id,
                            "affected_nodes": [node_id, dep_id],
                        },
                    )
                )

        except Exception as e:
            return Result(
                success=False, message=f"Operation failed: {e}", code=ErrorCode.INTERNAL_ERROR
            )

    def edit(
        self: ClientBase,
        node_id: str,
        *,
        state: str = "",
        summary: str = "",
        critical: dict[str, Any] | None = None,
        artifacts: str = "",
        context_merge: str = "merge",
        reason: str = "",
        op_id: str | None = None,
    ) -> Result:
        """Edit a node's properties."""
        cached = self._cached_op(op_id)
        if cached is not None:
            return cached
        try:
            with self._mutate(op_id) as tx:
                if node_id not in tx.graph.nodes:
                    return Result(
                        success=False,
                        message=f"Node {node_id} not found",
                        code=ErrorCode.TASK_NOT_FOUND,
                    )

                node = tx.graph.nodes[node_id]
                changes: list[str] = []

                if state:
                    try:
                        new_state = NodeState[state.upper()]
                    except KeyError:
                        valid = [s.name for s in NodeState]
                        return Result(
                            success=False,
                            message=f"Invalid state: {state}. Valid: {valid}",
                            code=ErrorCode.INVALID_INPUT,
                        )

                    old_state = node.state
                    if not old_state.can_transition_to(new_state):
                        return Result(
                            success=False,
                            message=f"Invalid transition: {old_state.name} -> {new_state.name}",
                            code=ErrorCode.INVALID_INPUT,
                        )

                    node.update_state(new_state)
                    changes.append(f"state: {old_state.name} -> {new_state.name}")

                    if new_state == NodeState.COMPLETED:
                        tx.graph.notify_completion(node_id)

                context_updated = _update_context(
                    node,
                    summary=summary,
                    critical=critical,
                    artifacts=artifacts,
                    merge_mode=context_merge,
                )
                if context_updated:
                    changes.append("context updated")

                if not changes:
                    return Result(
                        success=True,
                        message=f"No changes made to node {node_id}",
                        data={"node_id": node_id},
                    )

                edit_event_data: dict[str, Any] = {
                    "node_id": node_id,
                    "changes": changes,
                    "reason": reason,
                }
                if state:
                    edit_event_data["new_state"] = node.state.name
                if summary or critical is not None or artifacts:
                    edit_ctx: dict[str, Any] = {}
                    if summary:
                        edit_ctx["summary"] = summary
                    if critical is not None:
                        edit_ctx["critical"] = critical
                    if artifacts:
                        edit_ctx["artifacts_ref"] = self._storage.content.put(str(artifacts))
                    edit_event_data["context"] = edit_ctx
                tx.emit(EventType.NODE_EDITED, **edit_event_data)
                return tx.ok(
                    Result(
                        success=True,
                        message=f"Node {node_id} updated: {', '.join(changes)}",
                        data={"node_id": node_id, "state": node.state.name},
                    )
                )

        except Exception as e:
            return Result(
                success=False, message=f"Operation failed: {e}", code=ErrorCode.INTERNAL_ERROR
            )
