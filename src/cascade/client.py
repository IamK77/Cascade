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

"""Typed Python client for Cascade.

The single API layer for all Cascade operations. All business logic
lives here — tools and CLI are thin wrappers that delegate to this.

    from cascade.client import CascadeClient, Contract

    cascade = CascadeClient()
    cascade.add("analyze")
    cascade.add("impl", deps={"analyze": Contract("Need spec", "Deliver code")})

    task = cascade.claim("worker-1")
    # task.id, task.upstream, task.promises ...
    cascade.complete(task.id, summary="Done", critical={"lang": "python"})
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cascade.core.cascade import Cascade
from cascade.core.node import Node
from cascade.core.state import NodeState
from cascade.events import EventType
from cascade.operations.remove import RemoveOperation
from cascade.operations.rework import ReworkOperation
from cascade.operations.split import SplitOperation
from cascade.storage.file_storage import FileStorage, LockError
from cascade.storage.protocol import StorageProtocol
from cascade.storage.token_store import CancelNotifier
from cascade.types import Context, Contract, PromiseEntry, UpstreamEntry
from cascade.view import get_node_view

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class TaskView:
    """What an agent sees when claiming a task."""

    id: str
    state: str
    upstream: list[UpstreamEntry] = field(default_factory=list)
    promises: list[PromiseEntry] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)
    token: int | None = None


@dataclass
class NodeInfo:
    """Summary of a node's state."""

    id: str
    state: str
    pending_dependencies: int = 0
    agent_id: str | None = None
    active_seconds: float | None = None
    stale: bool = False


@dataclass
class Result:
    """Generic operation result.

    On failure, `code` carries a stable enum value so callers can branch
    programmatically without parsing `message`. See ErrorCode for the
    exhaustive list.
    """

    success: bool
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"success": self.success, "message": self.message, "data": self.data}
        if self.code:
            d["code"] = self.code
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Result:
        return cls(
            success=d["success"],
            message=d["message"],
            data=d.get("data", {}),
            code=d.get("code"),
        )


class ErrorCode:
    """Stable error codes for failure Results.

    Use these on every `Result(success=False, ...)` so consumers (agent
    prompts, scripts) can dispatch on a fixed enum rather than message text.
    """

    MISSING_AGENT_ID = "MISSING_AGENT_ID"
    TASK_NOT_FOUND = "TASK_NOT_FOUND"
    TASK_NOT_READY = "TASK_NOT_READY"
    TASK_ALREADY_ACTIVE = "TASK_ALREADY_ACTIVE"
    TASK_TERMINAL = "TASK_TERMINAL"
    TASK_NOT_ACTIVE = "TASK_NOT_ACTIVE"
    WRONG_AGENT = "WRONG_AGENT"
    ALREADY_HAS_ACTIVE = "ALREADY_HAS_ACTIVE"
    NO_READY_TASKS = "NO_READY_TASKS"
    LOCK_CONTENTION = "LOCK_CONTENTION"
    NODE_EXISTS = "NODE_EXISTS"
    DEP_NOT_FOUND = "DEP_NOT_FOUND"
    BATCH_INVALID_SPEC = "BATCH_INVALID_SPEC"
    INVALID_INPUT = "INVALID_INPUT"
    STALE_TOKEN = "STALE_TOKEN"
    INTERNAL_ERROR = "INTERNAL_ERROR"


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class CascadeClient:
    """Typed Python client for Cascade.

    The single API layer. All business logic lives in this class.
    Tools and CLI delegate here.
    """

    def __init__(self, storage: StorageProtocol | str | Path = ".cascade"):
        if isinstance(storage, (str, Path)):
            self._storage: StorageProtocol = FileStorage(storage)
        else:
            self._storage = storage

    def _check_op(self, op_id: str | None) -> Result | None:
        """If op_id was already executed, return the cached Result."""
        if op_id is None:
            return None
        cached = self._storage.ops.get(op_id)
        if cached is not None:
            return Result.from_dict(cached)
        return None

    def _record_op(self, op_id: str | None, result: Result) -> None:
        """Record an executed operation for idempotency."""
        if op_id is not None:
            self._storage.ops.record(op_id, result.to_dict())

    @property
    def storage(self) -> StorageProtocol:
        return self._storage

    # -- Structure ----------------------------------------------------------

    def add(
        self,
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
                Key is the dependency node_id, value is a Contract.
            dependents: Dependents with contracts.
                Key is the dependent node_id, value is a Contract.
            op_id: Idempotency key. Retries with the same op_id return cached result.
        """
        cached = self._check_op(op_id)
        if cached is not None:
            return cached
        try:
            with self._storage.lock():
                cascade = self._storage.load() or Cascade()
                r = self._add_locked(cascade, node_id, deps, dependents)
                if not r.success:
                    return r
                self._storage.events.emit(
                    EventType.NODE_ADDED,
                    logical_ts=self._storage.next_lamport(),
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
                self._storage.save(cascade)
                self._record_op(op_id, r)
                return r
        except Exception as e:
            return Result(
                success=False, message=f"Operation failed: {e}", code=ErrorCode.INTERNAL_ERROR
            )

    def add_batch(
        self,
        specs: list[dict[str, Any]],
    ) -> Result:
        """Atomically add multiple nodes in one lock acquisition.

        Each spec is `{"node_id": str, "deps": dict[str, Contract] | None,
        "dependents": dict[str, Contract] | None}`. If any node fails,
        no nodes are added and no events emitted — the operation is atomic.

        Order matters: a spec referencing a `dep` from an earlier spec is
        valid (the earlier one is added first, in the same lock).
        """
        if not specs:
            return Result(success=True, message="No nodes to add", data={"added": []})

        try:
            with self._storage.lock():
                cascade = self._storage.load() or Cascade()
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
                        cascade,
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
                    self._storage.events.emit(
                        EventType.NODE_ADDED,
                        logical_ts=self._storage.next_lamport(),
                        node_id=entry["node_id"],
                        dependencies=entry["deps"],
                        dependents=entry["dependents"],
                        deps_contracts=entry.get("deps_contracts", []),
                        dependent_contracts=entry.get("dependent_contracts", []),
                    )
                self._storage.save(cascade)

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
        self,
        cascade: Cascade,
        node_id: str,
        deps: dict[str, Contract] | None,
        dependents: dict[str, Contract] | None,
    ) -> Result:
        """Single-node add operating on an already-loaded cascade graph.

        Does not acquire lock, save, or emit events. Caller is responsible.
        """
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
        self,
        node_id: str,
        *,
        cascade: bool = False,
        reason: str = "",
    ) -> Result:
        """Remove a node from the DAG.

        Args:
            node_id: Node to remove.
            cascade: Also remove all dependents.
            reason: Why -- recorded in event log.
        """
        try:
            with self._storage.lock():
                graph = self._storage.load() or Cascade()

                if node_id not in graph.nodes:
                    return Result(
                        success=False,
                        message=f"Node {node_id} not found",
                        code=ErrorCode.TASK_NOT_FOUND,
                    )

                node = graph.nodes[node_id]
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
                        for dep in graph.get_dependents(node_id)
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

                operation = RemoveOperation(graph)
                result = operation.execute(node_id=node_id, cascade=cascade)

                if result.success:
                    self._storage.events.emit(
                        EventType.NODE_REMOVED,
                        logical_ts=self._storage.next_lamport(),
                        node_id=node_id,
                        cascade=cascade,
                        affected_nodes=result.affected_nodes,
                        reason=reason,
                    )
                self._storage.save(graph)
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
        self,
        node_id: str,
        into: list[str],
        *,
        reason: str = "",
    ) -> Result:
        """Split a node into multiple subtasks.

        Args:
            node_id: Node to split (must not be ACTIVE).
            into: List of new node IDs to replace it.
            reason: Why -- recorded in event log.
        """
        if not into:
            return Result(
                success=False,
                message="new_nodes must be a non-empty list",
                code=ErrorCode.INVALID_INPUT,
            )

        try:
            with self._storage.lock():
                graph = self._storage.load() or Cascade()

                if node_id not in graph.nodes:
                    return Result(
                        success=False,
                        message=f"Parent node {node_id} not found",
                        code=ErrorCode.TASK_NOT_FOUND,
                    )

                parent = graph.nodes[node_id]
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

                operation = SplitOperation(graph)
                result = operation.execute(parent_id=node_id, new_nodes=new_nodes)

                if result.success:
                    self._storage.events.emit(
                        EventType.NODE_SPLIT,
                        logical_ts=self._storage.next_lamport(),
                        node_id=node_id,
                        new_node_ids=result.data.new_node_ids if result.data else [],
                        reason=reason,
                    )
                self._storage.save(graph)
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
        self,
        node_id: str,
        dep_id: str,
        expectation: str,
        promise: str,
        *,
        reason: str = "",
    ) -> Result:
        """Add a dependency to an existing node.

        Args:
            node_id: Node that needs the dependency.
            dep_id: The dependency node.
            expectation: What node_id needs from dep_id.
            promise: What dep_id delivers.
            reason: Why -- recorded in event log.
        """
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

        try:
            with self._storage.lock():
                graph = self._storage.load() or Cascade()

                if node_id not in graph.nodes:
                    return Result(
                        success=False,
                        message=f"Node {node_id} not found",
                        code=ErrorCode.TASK_NOT_FOUND,
                    )
                if dep_id not in graph.nodes:
                    return Result(
                        success=False,
                        message=f"Dependency {dep_id} not found. Create it first with add_node.",
                        code=ErrorCode.DEP_NOT_FOUND,
                    )

                if graph.has_dependency(node_id, dep_id):
                    return Result(
                        success=False,
                        message=f"Node {node_id} already depends on {dep_id}",
                        code=ErrorCode.INVALID_INPUT,
                    )

                if graph._has_path(node_id, dep_id):
                    return Result(
                        success=False,
                        message=f"Adding dependency {dep_id} to {node_id} would create a cycle",
                        code=ErrorCode.INVALID_INPUT,
                    )

                graph.add_edge(dep_id, node_id, expectation=expectation, promise=promise)

                self._storage.events.emit(
                    EventType.NODE_REFINED,
                    logical_ts=self._storage.next_lamport(),
                    node_id=node_id,
                    dependency_id=dep_id,
                    expectation=expectation,
                    promise=promise,
                    reason=reason,
                )
                self._storage.save(graph)
                return Result(
                    success=True,
                    message=f"Node {node_id} now depends on {dep_id}",
                    data={
                        "node_id": node_id,
                        "dependency_id": dep_id,
                        "affected_nodes": [node_id, dep_id],
                    },
                )

        except Exception as e:
            return Result(
                success=False, message=f"Operation failed: {e}", code=ErrorCode.INTERNAL_ERROR
            )

    def edit(
        self,
        node_id: str,
        *,
        state: str = "",
        summary: str = "",
        critical: dict[str, Any] | None = None,
        artifacts: str = "",
        context_merge: str = "merge",
        reason: str = "",
    ) -> Result:
        """Edit a node's properties.

        Args:
            node_id: Node to edit.
            state: New state (e.g. "READY", "CANCELLED").
            summary: Update summary text.
            critical: Update critical KV data.
            artifacts: Update artifacts content.
            context_merge: How to merge context: "replace", "merge", "append".
            reason: Why -- recorded in event log.
        """
        try:
            with self._storage.lock():
                graph = self._storage.load() or Cascade()

                if node_id not in graph.nodes:
                    return Result(
                        success=False,
                        message=f"Node {node_id} not found",
                        code=ErrorCode.TASK_NOT_FOUND,
                    )

                node = graph.nodes[node_id]
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
                        graph.notify_completion(node_id)

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
                        edit_ctx["artifacts"] = artifacts
                    edit_event_data["context"] = edit_ctx
                self._storage.events.emit(
                    EventType.NODE_EDITED,
                    logical_ts=self._storage.next_lamport(),
                    **edit_event_data,
                )
                self._storage.save(graph)
                return Result(
                    success=True,
                    message=f"Node {node_id} updated: {', '.join(changes)}",
                    data={"node_id": node_id, "state": node.state.name},
                )

        except Exception as e:
            return Result(
                success=False, message=f"Operation failed: {e}", code=ErrorCode.INTERNAL_ERROR
            )

    # -- Execution ----------------------------------------------------------

    def claim(
        self,
        agent_id: str,
        task_id: str | None = None,
        *,
        timeout: float | None = None,
        cancel_notifier: CancelNotifier | None = None,
    ) -> TaskView:
        """Claim a task to work on.

        Args:
            agent_id: Unique agent identifier.
            task_id: Specific task to claim (or None for highest-priority READY).
            timeout: Auto-release after this many seconds.
            cancel_notifier: Push notification on cancellation.

        Returns:
            TaskView with task info, upstream context, and promises.

        Raises:
            RuntimeError: If no task available or claim fails.
        """
        r = self._claim_inner(agent_id, task_id, timeout=timeout, cancel_notifier=cancel_notifier)
        if not r.success:
            raise RuntimeError(r.message)

        info = r.data.get("task_info", {})
        return TaskView(
            id=r.data["task_id"],
            state=r.data["state"],
            upstream=info.get("upstream", []),
            promises=info.get("promises", []),
            raw=info,
            token=r.data.get("token"),
        )

    def _claim_inner(
        self,
        agent_id: str,
        task_id: str | None = None,
        *,
        timeout: float | None = None,
        cancel_notifier: CancelNotifier | None = None,
    ) -> Result:
        """Internal claim logic returning a Result (used by tool wrappers).

        Retries on lock contention with exponential backoff (3 attempts total),
        since concurrent get-task calls from parallel workers are a primary use case.
        """
        if not agent_id:
            return Result(
                success=False,
                message="agent_id is required. Each agent can only hold ONE task at a time.",
                code=ErrorCode.MISSING_AGENT_ID,
            )

        backoffs = [0.1, 0.4, 1.6]
        for attempt in range(len(backoffs) + 1):
            try:
                return self._claim_locked(
                    agent_id, task_id, timeout=timeout, cancel_notifier=cancel_notifier
                )
            except LockError:
                if attempt < len(backoffs):
                    time.sleep(backoffs[attempt])
                    continue
                return Result(
                    success=False,
                    message=(
                        f"Could not acquire lock after {len(backoffs) + 1} attempts. "
                        "Another agent may be holding it for an extended period."
                    ),
                    code=ErrorCode.LOCK_CONTENTION,
                )
            except Exception as e:
                return Result(
                    success=False, message=f"Operation failed: {e}", code=ErrorCode.INTERNAL_ERROR
                )

        return Result(
            success=False, message="claim retry exhausted", code=ErrorCode.LOCK_CONTENTION
        )

    def _claim_locked(
        self,
        agent_id: str,
        task_id: str | None,
        *,
        timeout: float | None,
        cancel_notifier: CancelNotifier | None,
    ) -> Result:
        """Single-attempt claim — raises LockError on lock contention."""
        with self._storage.lock():
            graph = self._storage.load() or Cascade()

            existing_node = graph.find_agent_active_task(agent_id)
            if existing_node:
                # Agent already holds an active task — return failure so callers
                # can branch on `code` rather than receiving a misleading success
                # with the briefing of a different task.
                return Result(
                    success=False,
                    message=(
                        f"Agent {agent_id} already holds active task "
                        f"'{existing_node.id}'. Finish it before claiming a new one."
                    ),
                    data={
                        "current_task": existing_node.id,
                        "state": "ACTIVE",
                    },
                    code=ErrorCode.ALREADY_HAS_ACTIVE,
                )

            if task_id:
                if task_id not in graph.nodes:
                    return Result(
                        success=False,
                        message=f"Task {task_id} not found",
                        code=ErrorCode.TASK_NOT_FOUND,
                    )

                node = graph.nodes[task_id]

                if node.agent_id and node.agent_id != agent_id and node.state == NodeState.ACTIVE:
                    return Result(
                        success=False,
                        message=f"Task {task_id} is already being executed by agent: {node.agent_id}",
                        data={"state": "ACTIVE", "assigned_to": node.agent_id},
                        code=ErrorCode.TASK_ALREADY_ACTIVE,
                    )

                if node.state == NodeState.ACTIVE:
                    node.agent_id = agent_id
                    task_info = get_node_view(graph, task_id)
                    self._storage.save(graph)
                    return Result(
                        success=True,
                        message=f"Task {task_id} is already active",
                        data={"task_id": task_id, "state": "ACTIVE", "task_info": task_info},
                    )

                if node.state.is_terminal():
                    return Result(
                        success=False,
                        message=f"Task {task_id} is in terminal state: {node.state.name}",
                        data={"state": node.state.name},
                        code=ErrorCode.TASK_TERMINAL,
                    )

                if node.state == NodeState.PENDING:
                    pending = graph.pending_dependency_count(task_id)
                    return Result(
                        success=False,
                        message=f"Task {task_id} is not ready (dependencies not met, pending={pending})",
                        data={"state": "PENDING", "pending_dependencies": pending},
                        code=ErrorCode.TASK_NOT_READY,
                    )

                node.update_state(NodeState.ACTIVE)
                node.agent_id = agent_id
                node.claimed_at = time.time()
                if timeout is not None:
                    node.timeout = float(timeout)

            else:
                ready_nodes = graph.get_ready_nodes()

                if not ready_nodes:
                    active_count = sum(
                        1 for n in graph.nodes.values() if n.state == NodeState.ACTIVE
                    )
                    pending_count = sum(
                        1 for n in graph.nodes.values() if n.state == NodeState.PENDING
                    )

                    if active_count > 0:
                        return Result(
                            success=False,
                            message=f"No available tasks. {active_count} task(s) are executed, {pending_count} pending.",
                            data={"active": active_count, "pending": pending_count},
                            code=ErrorCode.NO_READY_TASKS,
                        )
                    else:
                        return Result(
                            success=False,
                            message=f"No available tasks. All {pending_count} tasks are pending (dependencies not met).",
                            data={"pending": pending_count},
                            code=ErrorCode.NO_READY_TASKS,
                        )

                node = ready_nodes[0]
                task_id = node.id
                node.update_state(NodeState.ACTIVE)
                node.agent_id = agent_id
                node.claimed_at = time.time()
                if timeout is not None:
                    node.timeout = float(timeout)

            token = graph.increment_epoch()
            task_info = get_node_view(graph, task_id)
            self._storage.tokens.create(
                task_id, agent_id, node.claimed_at, notifier=cancel_notifier
            )
            self._storage.events.emit(
                EventType.TASK_CLAIMED,
                logical_ts=self._storage.next_lamport(),
                node_id=task_id,
                agent_id=agent_id,
                claimed_at=node.claimed_at,
                timeout=node.timeout,
            )
            self._storage.save(graph)

            return Result(
                success=True,
                message=f"Task {task_id} assigned (state: ACTIVE)",
                data={
                    "task_id": task_id,
                    "state": "ACTIVE",
                    "task_info": task_info,
                    "assigned_to": agent_id,
                    "token": token,
                },
            )

    def complete(
        self,
        task_id: str,
        *,
        agent_id: str | None = None,
        token: int | None = None,
        op_id: str | None = None,
        summary: str = "",
        critical: dict[str, Any] | None = None,
        artifacts: str = "",
    ) -> Result:
        """Mark a task as successfully completed.

        Args:
            task_id: Task to complete.
            agent_id: Agent calling finish — must match the claiming agent.
            token: Fencing token from claim. If provided, rejects stale writes.
            op_id: Idempotency key. Retries with the same op_id return cached result.
            summary: Brief description of what was done (2-hop propagation).
            critical: Structured KV data for downstream (infinite propagation).
            artifacts: Full content (infinite propagation).
        """
        return self._finish(
            task_id,
            agent_id=agent_id,
            token=token,
            op_id=op_id,
            is_success=True,
            is_release=False,
            summary=summary,
            critical=critical,
            artifacts=artifacts,
        )

    def fail(
        self,
        task_id: str,
        *,
        agent_id: str | None = None,
        token: int | None = None,
        op_id: str | None = None,
        reason: str = "",
        cascade: bool = False,
    ) -> Result:
        """Mark a task as failed.

        Args:
            task_id: Task that failed.
            agent_id: Agent calling finish — must match the claiming agent.
            token: Fencing token from claim. If provided, rejects stale writes.
            op_id: Idempotency key. Retries with the same op_id return cached result.
            reason: What went wrong.
            cascade: Also fail all dependent tasks.
        """
        return self._finish(
            task_id,
            agent_id=agent_id,
            token=token,
            op_id=op_id,
            is_success=False,
            is_release=False,
            summary=reason,
            should_cascade=cascade,
        )

    def release(
        self,
        task_id: str,
        *,
        agent_id: str | None = None,
        token: int | None = None,
        op_id: str | None = None,
        reason: str = "",
    ) -> Result:
        """Release a task back to READY.

        Args:
            task_id: Task to release.
            agent_id: Agent calling release — must match the claiming agent.
            token: Fencing token from claim. If provided, rejects stale writes.
            op_id: Idempotency key. Retries with the same op_id return cached result.
            reason: Why the agent is giving up.
        """
        return self._finish(
            task_id,
            agent_id=agent_id,
            token=token,
            op_id=op_id,
            is_success=False,
            is_release=True,
            summary=reason,
        )

    def _finish(
        self,
        task_id: str,
        *,
        agent_id: str | None = None,
        token: int | None = None,
        op_id: str | None = None,
        is_success: bool = True,
        is_release: bool = False,
        summary: str = "",
        critical: dict[str, Any] | None = None,
        artifacts: str = "",
        should_cascade: bool = False,
    ) -> Result:
        """Internal finish logic shared by complete/fail/release."""
        cached = self._check_op(op_id)
        if cached is not None:
            return cached
        try:
            with self._storage.lock():
                graph = self._storage.load() or Cascade()

                if token is not None and token < graph.epoch:
                    return Result(
                        success=False,
                        message=(
                            f"Stale fencing token: provided {token}, "
                            f"current epoch is {graph.epoch}. "
                            f"The graph has been modified since this task was claimed."
                        ),
                        data={"provided_token": token, "current_epoch": graph.epoch},
                        code=ErrorCode.STALE_TOKEN,
                    )

                if task_id not in graph.nodes:
                    return Result(
                        success=False,
                        message=f"Task {task_id} not found",
                        code=ErrorCode.TASK_NOT_FOUND,
                    )

                node = graph.nodes[task_id]

                if node.state != NodeState.ACTIVE:
                    return Result(
                        success=False,
                        message=f"Task {task_id} is not active (current: {node.state.name})",
                        data={"state": node.state.name},
                        code=ErrorCode.TASK_NOT_ACTIVE,
                    )

                if agent_id is not None and node.agent_id != agent_id:
                    return Result(
                        success=False,
                        message=(
                            f"Task {task_id} is claimed by '{node.agent_id}', "
                            f"not '{agent_id}'. Only the claiming agent can finish it."
                        ),
                        data={"claimed_by": node.agent_id, "caller": agent_id},
                        code=ErrorCode.WRONG_AGENT,
                    )

                graph.increment_epoch()

                if is_release:
                    node.update_state(NodeState.READY)
                    node.agent_id = None
                    node.claimed_at = None
                    node.timeout = None

                    message = f"Task {task_id} released and is now available"
                    if summary:
                        message += f" (reason: {summary})"

                    self._storage.tokens.invalidate(task_id, reason="released")
                    self._storage.events.emit(
                        EventType.TASK_RELEASED,
                        logical_ts=self._storage.next_lamport(),
                        node_id=task_id,
                        reason=summary,
                    )
                    self._storage.save(graph)
                    r = Result(
                        success=True,
                        message=message,
                        data={"task_id": task_id, "outcome": "RELEASED", "state": "READY"},
                    )
                    self._record_op(op_id, r)
                    return r

                elif is_success:
                    node.update_state(NodeState.COMPLETED)
                    node.agent_id = None
                    node.claimed_at = None
                    node.timeout = None

                    if summary or critical or artifacts:
                        if node.context is None:
                            node.context = Context()
                        if summary:
                            node.context.summary = summary
                        if critical and isinstance(critical, dict):
                            node.context.critical.update(critical)
                        if artifacts:
                            node.context.artifacts = str(artifacts)

                    unblocked = graph.notify_completion(task_id)

                    message = f"Task {task_id} completed"
                    if unblocked:
                        message += f", unblocked: {unblocked}"

                    self._storage.tokens.cleanup(task_id)
                    ctx_data: dict[str, Any] = {}
                    if summary:
                        ctx_data["summary"] = summary
                    if critical:
                        ctx_data["critical"] = critical
                    if artifacts:
                        ctx_data["artifacts"] = artifacts
                    self._storage.events.emit(
                        EventType.TASK_COMPLETED,
                        logical_ts=self._storage.next_lamport(),
                        node_id=task_id,
                        unblocked=unblocked,
                        context=ctx_data if ctx_data else None,
                    )
                    self._storage.save(graph)
                    r = Result(
                        success=True,
                        message=message,
                        data={
                            "task_id": task_id,
                            "outcome": "COMPLETED",
                            "unblocked_tasks": unblocked,
                        },
                    )
                    self._record_op(op_id, r)
                    return r

                else:
                    affected = [task_id]
                    node.agent_id = None

                    if should_cascade:

                        def fail_recursive(nid: str) -> None:
                            current = graph.nodes[nid]
                            if current.state.is_terminal():
                                return
                            current.update_state(NodeState.FAILED)
                            current.agent_id = None
                            current.claimed_at = None
                            current.timeout = None
                            affected.append(nid)
                            for dep in graph.get_dependents(nid):
                                fail_recursive(dep.id)

                        fail_recursive(task_id)
                    else:
                        node.update_state(NodeState.FAILED)

                    message = f"Task {task_id} failed"
                    if should_cascade and len(affected) > 1:
                        message += f" (cascaded to {len(affected) - 1} dependent tasks)"
                    if summary:
                        message += f": {summary}"

                    self._storage.tokens.cleanup(task_id)
                    self._storage.events.emit(
                        EventType.TASK_FAILED,
                        logical_ts=self._storage.next_lamport(),
                        node_id=task_id,
                        reason=summary,
                        affected=affected,
                        cascade=should_cascade,
                    )
                    self._storage.save(graph)
                    r = Result(
                        success=True,
                        message=message,
                        data={
                            "task_id": task_id,
                            "outcome": "FAILED",
                            "affected_tasks": affected,
                            "cascade": should_cascade,
                        },
                    )
                    self._record_op(op_id, r)
                    return r

        except Exception as e:
            return Result(
                success=False, message=f"Operation failed: {e}", code=ErrorCode.INTERNAL_ERROR
            )

    # -- Feedback -----------------------------------------------------------

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
        """Request rework of an upstream node's output.

        Args:
            source: The upstream node whose output is wrong.
            corrective: ID for the new corrective node.
            reason: What's wrong with the source output.
            agent_id: The agent requesting rework (must own an active task).
            source_expectation: What corrective expects from source.
            source_promise: What source promises to corrective.
            corrective_expectation: What requester expects from corrective.
            corrective_promise: What corrective promises to requester.
        """
        if not source:
            return Result(
                success=False,
                message="Missing required parameter: source_node_id",
                code=ErrorCode.INVALID_INPUT,
            )
        if not corrective:
            return Result(
                success=False,
                message="Missing required parameter: corrective_node_id",
                code=ErrorCode.INVALID_INPUT,
            )
        if not reason:
            return Result(
                success=False,
                message="Missing required parameter: reason",
                code=ErrorCode.INVALID_INPUT,
            )
        if not agent_id:
            return Result(
                success=False,
                message="Missing required parameter: agent_id",
                code=ErrorCode.INVALID_INPUT,
            )
        if not source_expectation:
            return Result(
                success=False,
                message="Missing required parameter: source_expectation",
                code=ErrorCode.INVALID_INPUT,
            )
        if not source_promise:
            return Result(
                success=False,
                message="Missing required parameter: source_promise",
                code=ErrorCode.INVALID_INPUT,
            )
        if not corrective_expectation:
            return Result(
                success=False,
                message="Missing required parameter: corrective_expectation",
                code=ErrorCode.INVALID_INPUT,
            )
        if not corrective_promise:
            return Result(
                success=False,
                message="Missing required parameter: corrective_promise",
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
            with self._storage.lock():
                graph = self._storage.load() or Cascade()

                active_node = graph.find_agent_active_task(agent_id)
                if not active_node:
                    return Result(
                        success=False,
                        message=f"Agent '{agent_id}' has no active task to request rework from",
                        code=ErrorCode.TASK_NOT_ACTIVE,
                    )

                operation = ReworkOperation(graph)
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
                    self._storage.events.emit(
                        EventType.REWORK_REQUESTED,
                        logical_ts=self._storage.next_lamport(),
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
                    self._storage.save(graph)

                return Result(
                    success=result.success,
                    message=result.message,
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

    # -- Query --------------------------------------------------------------

    def nodes(self, state: str | None = None) -> list[NodeInfo]:
        """List all tasks in the DAG.

        Args:
            state: Filter by state (e.g. "READY", "ACTIVE").
        """
        r = self._nodes_inner(state_filter=state)
        return [
            NodeInfo(
                id=n["id"],
                state=n["state"],
                pending_dependencies=n.get("pending_dependencies", 0),
                agent_id=n.get("agent_id"),
                active_seconds=n.get("active_seconds"),
                stale=n.get("stale", False),
            )
            for n in r.data.get("nodes", [])
        ]

    def _nodes_inner(
        self,
        *,
        state_filter: str | None = None,
        include_pending_only: bool = False,
    ) -> Result:
        """Internal list_nodes logic returning a Result (used by tool wrappers)."""
        try:
            with self._storage.lock():
                graph = self._storage.load() or Cascade()

                nodes_list: list[dict[str, Any]] = []
                by_state: dict[str, list[str]] = {}

                now = time.time()
                for nid, node in graph.nodes.items():
                    if state_filter and node.state.name != state_filter:
                        continue
                    if include_pending_only and node.state.name != "PENDING":
                        continue

                    pending = graph.pending_dependency_count(nid)
                    node_info: dict[str, Any] = {
                        "id": node.id,
                        "state": node.state.name,
                        "pending_dependencies": pending,
                    }

                    if node.state == NodeState.ACTIVE:
                        if node.agent_id:
                            node_info["agent_id"] = node.agent_id
                        if node.claimed_at is not None:
                            elapsed = now - node.claimed_at
                            node_info["active_seconds"] = round(elapsed, 1)
                            if node.is_timed_out(now):
                                node_info["stale"] = True
                            elif node.timeout is None and elapsed > 600:
                                node_info["stale"] = True

                    nodes_list.append(node_info)

                    state_name = node.state.name
                    if state_name not in by_state:
                        by_state[state_name] = []
                    by_state[state_name].append(nid)

                return Result(
                    success=True,
                    message=f"Listed {len(nodes_list)} nodes",
                    data={
                        "nodes": nodes_list,
                        "count": len(nodes_list),
                        "by_state": by_state,
                    },
                )

        except Exception as e:
            return Result(
                success=False,
                message=f"Failed to list nodes: {e}",
                data={"nodes": [], "count": 0, "by_state": {}},
                code=ErrorCode.INTERNAL_ERROR,
            )

    def check(self, task_id: str) -> Result:
        """Check if a task claim is still valid (pull cancellation).

        Args:
            task_id: Task to check.
        """
        if not task_id:
            return Result(
                success=False,
                message="Missing required parameter: task_id",
                code=ErrorCode.INVALID_INPUT,
            )

        token = self._storage.tokens.check(task_id)
        if token is None:
            return Result(
                success=True,
                message=f"No active claim for task {task_id}",
                data={"task_id": task_id, "valid": False, "reason": "no_token"},
            )

        return Result(
            success=True,
            message=f"Task {task_id}: {'valid' if token.valid else 'invalidated'}",
            data={
                "task_id": token.node_id,
                "agent_id": token.agent_id,
                "valid": token.valid,
                "claimed_at": token.claimed_at,
                "reason": token.reason,
                "invalidated_at": token.invalidated_at,
            },
        )

    def check_timeouts(self, default_timeout: float | None = None) -> Result:
        """Release stalled tasks that exceeded their timeout.

        Args:
            default_timeout: Timeout in seconds for tasks without explicit timeout.
        """
        try:
            with self._storage.lock():
                graph = self._storage.load() or Cascade()

                now = time.time()
                released: list[dict[str, Any]] = []

                for node in graph.nodes.values():
                    if node.state != NodeState.ACTIVE:
                        continue
                    if node.claimed_at is None:
                        continue

                    effective_timeout = node.timeout or default_timeout
                    if effective_timeout is None:
                        continue

                    elapsed = now - node.claimed_at
                    if elapsed < effective_timeout:
                        continue

                    old_agent = node.agent_id
                    node.update_state(NodeState.READY)
                    node.agent_id = None
                    node.claimed_at = None
                    node.timeout = None

                    released.append(
                        {
                            "task_id": node.id,
                            "agent_id": old_agent,
                            "elapsed_seconds": round(elapsed, 1),
                            "timeout_seconds": effective_timeout,
                        }
                    )
                    self._storage.tokens.invalidate(node.id, reason="timed_out")
                    self._storage.events.emit(
                        EventType.TASK_TIMED_OUT,
                        logical_ts=self._storage.next_lamport(),
                        node_id=node.id,
                        agent_id=old_agent,
                        elapsed=round(elapsed, 1),
                    )

                if released:
                    self._storage.save(graph)

                return Result(
                    success=True,
                    message=(
                        f"Released {len(released)} timed-out task(s)"
                        if released
                        else "No timed-out tasks found"
                    ),
                    data={
                        "released": released,
                        "count": len(released),
                    },
                )

        except Exception as e:
            return Result(
                success=False, message=f"Operation failed: {e}", code=ErrorCode.INTERNAL_ERROR
            )

    def history(
        self,
        *,
        node_id: str = "",
        event_type: str = "",
        last_n: int = 0,
        summary: bool = False,
    ) -> Result:
        """Query the event log.

        Args:
            node_id: Filter by node.
            event_type: Filter by event type.
            last_n: Return only last N events.
            summary: Return counts by type instead of events.
        """
        try:
            event_store = self._storage.events

            if summary:
                counts = event_store.summary()
                return Result(
                    success=True,
                    message=f"{sum(counts.values())} total events",
                    data={"summary": counts, "total": sum(counts.values())},
                )

            if node_id:
                events = event_store.read_by_node(node_id)
            elif event_type:
                try:
                    et = EventType(event_type)
                except ValueError:
                    valid = [e.value for e in EventType]
                    return Result(
                        success=False,
                        message=f"Invalid event_type: {event_type}. Valid: {valid}",
                        code=ErrorCode.INVALID_INPUT,
                    )
                events = event_store.read_by_type(et)
            else:
                events = event_store.read_all()

            if last_n and isinstance(last_n, int) and last_n > 0:
                events = events[-last_n:]

            formatted = []
            for event in events:
                ts = datetime.fromtimestamp(event.timestamp, tz=UTC).isoformat()
                entry: dict[str, Any] = {
                    "type": event.type.value,
                    "timestamp": ts,
                    "data": event.data,
                }
                if event.id:
                    entry["id"] = event.id
                if event.logical_ts:
                    entry["logical_ts"] = event.logical_ts
                formatted.append(entry)

            return Result(
                success=True,
                message=f"{len(formatted)} event(s)",
                data={"events": formatted, "count": len(formatted)},
            )

        except Exception as e:
            return Result(
                success=False, message=f"Failed to read history: {e}", code=ErrorCode.INTERNAL_ERROR
            )


# ---------------------------------------------------------------------------
# Helpers (module-private)
# ---------------------------------------------------------------------------


def _update_context(
    node: Node,
    *,
    summary: str = "",
    critical: dict[str, Any] | None = None,
    artifacts: str = "",
    merge_mode: str = "merge",
) -> bool:
    """Update node context based on params. Returns True if context was updated."""
    if critical is None and not summary and not artifacts:
        return False

    if node.context is None:
        node.context = Context()

    ctx = node.context

    if merge_mode == "replace":
        if critical is not None:
            ctx.critical = dict(critical)
        if summary:
            ctx.summary = summary
        if artifacts:
            ctx.artifacts = str(artifacts)
    elif merge_mode == "append":
        if critical is not None and isinstance(critical, dict):
            ctx.critical.update(critical)
        if summary:
            ctx.summary = (ctx.summary + "\n" + summary).strip()
        if artifacts:
            ctx.artifacts = str(artifacts)
    else:  # merge (default)
        if critical is not None and isinstance(critical, dict):
            ctx.critical.update(critical)
        if summary:
            if ctx.summary:
                ctx.summary = ctx.summary + "\n" + summary
            else:
                ctx.summary = summary
        if artifacts:
            ctx.artifacts = str(artifacts)

    return True
