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

"""Client mixin — task execution lifecycle (claim, complete, fail, release)."""

from __future__ import annotations

import time
from typing import Any

from cascade import tips
from cascade.client.base import ClientBase, _get_git_ref
from cascade.core.state import NodeState
from cascade.errors import LockError
from cascade.events import EventType
from cascade.storage.token_store import CancelNotifier
from cascade.types import (
    Context,
    ErrorCode,
    Provenance,
    Result,
)
from cascade.view import get_node_view


class ExecutionMixin(ClientBase):
    """Task execution lifecycle: claim, complete, fail, release."""

    def claim(
        self,
        agent_id: str,
        task_id: str | None = None,
        *,
        timeout: float | None = None,
        cancel_notifier: CancelNotifier | None = None,
    ) -> Result:
        """Claim a task to work on.

        Args:
            agent_id: Unique agent identifier.
            task_id: Specific task to claim (or None for highest-priority READY).
            timeout: Auto-release after this many seconds.
            cancel_notifier: Push notification on cancellation.
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
        with self._mutate() as tx:
            graph = tx.graph

            existing_node = graph.find_agent_active_task(agent_id)
            if existing_node:
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
                    tx.save()
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
            tx.emit(
                EventType.TASK_CLAIMED,
                node_id=task_id,
                agent_id=agent_id,
                claimed_at=node.claimed_at,
                timeout=node.timeout,
            )
            tx.save()

            released_events = self._storage.events.read_by_node(task_id)
            was_released = any(e.type == EventType.TASK_RELEASED for e in released_events)

            claim_tips = tips.on_claim(
                task_id=task_id,
                upstream=task_info.get("upstream", []),
                promises=task_info.get("promises", []),
                was_previously_released=was_released,
            )

            return Result(
                success=True,
                message=tips.append_tips(f"Task {task_id} assigned (state: ACTIVE)", claim_tips),
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
        deliverables: dict[str, str] | None = None,
    ) -> Result:
        """Mark a task as successfully completed."""
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
            deliverables=deliverables,
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
        """Mark a task as failed."""
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
        """Release a task back to READY."""
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
        deliverables: dict[str, str] | None = None,
        should_cascade: bool = False,
    ) -> Result:
        """Internal finish logic shared by complete/fail/release."""
        if token is None:
            return Result(
                success=False,
                message=(
                    "Fencing token is required. "
                    "Call get-task first to claim the task and receive a token."
                ),
                code=ErrorCode.STALE_TOKEN,
            )
        cached = self._cached_op(op_id)
        if cached is not None:
            return cached
        try:
            with self._mutate(op_id) as tx:
                if token < tx.graph.epoch:
                    return Result(
                        success=False,
                        message=(
                            f"Stale fencing token: provided {token}, "
                            f"current epoch is {tx.graph.epoch}. "
                            f"The graph has been modified since this task was claimed."
                        ),
                        data={"provided_token": token, "current_epoch": tx.graph.epoch},
                        code=ErrorCode.STALE_TOKEN,
                    )

                if task_id not in tx.graph.nodes:
                    return Result(
                        success=False,
                        message=f"Task {task_id} not found",
                        code=ErrorCode.TASK_NOT_FOUND,
                    )

                node = tx.graph.nodes[task_id]

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

                tx.graph.increment_epoch()

                if is_release:
                    node.update_state(NodeState.READY)
                    node.agent_id = None
                    node.claimed_at = None
                    node.timeout = None

                    message = f"Task {task_id} released and is now available"
                    if summary:
                        message += f" (reason: {summary})"

                    self._storage.tokens.invalidate(task_id, reason="released")
                    tx.emit(EventType.TASK_RELEASED, node_id=task_id, reason=summary)
                    return tx.ok(
                        Result(
                            success=True,
                            message=message,
                            data={"task_id": task_id, "outcome": "RELEASED", "state": "READY"},
                        )
                    )

                elif is_success:
                    node_promises = tx.graph.get_node_promises(task_id)
                    complete_tips = tips.on_complete(
                        summary=summary,
                        critical=critical or {},
                        artifacts=artifacts,
                        promises=[
                            {"to_node": p["to_node"], "promise": p["promise"]}
                            for p in node_promises
                        ],
                        deliverables=deliverables,
                        has_dependents=len(tx.graph.get_dependents(task_id)) > 0,
                    )

                    if tips.has_required(complete_tips):
                        return Result(
                            success=False,
                            message=tips.required_messages(complete_tips)[0],
                            code=ErrorCode.UNADDRESSED_PROMISES,
                        )

                    node.update_state(NodeState.COMPLETED)
                    node.agent_id = None
                    node.claimed_at = None
                    node.timeout = None

                    if node.context is None:
                        node.context = Context()
                    if summary:
                        node.context.summary = summary
                    if critical:
                        node.context.critical.update(critical)
                    if artifacts:
                        node.context.artifacts = str(artifacts)

                    prov = Provenance(produced_at=time.time())
                    git_ref = _get_git_ref()
                    if git_ref:
                        prov.git_ref = git_ref
                    if deliverables:
                        prov.deliverables = deliverables
                    node.context.provenance = prov

                    unblocked = tx.graph.notify_completion(task_id)

                    message = f"Task {task_id} completed"
                    if unblocked:
                        message += f", unblocked: {unblocked}"
                    message = tips.append_tips(message, complete_tips)

                    self._storage.tokens.cleanup(task_id)
                    ctx_data: dict[str, Any] = {}
                    if summary:
                        ctx_data["summary"] = summary
                    if critical:
                        ctx_data["critical"] = critical
                    if artifacts:
                        ctx_data["artifacts_ref"] = self._storage.content.put(str(artifacts))
                    tx.emit(
                        EventType.TASK_COMPLETED,
                        node_id=task_id,
                        unblocked=unblocked,
                        context=ctx_data if ctx_data else None,
                    )
                    return tx.ok(
                        Result(
                            success=True,
                            message=message,
                            data={
                                "task_id": task_id,
                                "outcome": "COMPLETED",
                                "unblocked_tasks": unblocked,
                            },
                        )
                    )

                else:
                    affected = [task_id]
                    node.agent_id = None
                    node.claimed_at = None
                    node.timeout = None

                    if should_cascade:

                        def fail_recursive(nid: str) -> None:
                            current = tx.graph.nodes[nid]
                            if current.state.is_terminal():
                                return
                            current.update_state(NodeState.FAILED)
                            current.agent_id = None
                            current.claimed_at = None
                            current.timeout = None
                            affected.append(nid)
                            for dep in tx.graph.get_dependents(nid):
                                fail_recursive(dep.id)

                        fail_recursive(task_id)
                    else:
                        node.update_state(NodeState.FAILED)

                    message = f"Task {task_id} failed"
                    if should_cascade and len(affected) > 1:
                        message += f" (cascaded to {len(affected) - 1} dependent tasks)"
                    if summary:
                        message += f": {summary}"

                    fail_tips = tips.on_fail(
                        cascade=should_cascade,
                        affected_count=len(affected),
                    )
                    message = tips.append_tips(message, fail_tips)

                    self._storage.tokens.cleanup(task_id)
                    tx.emit(
                        EventType.TASK_FAILED,
                        node_id=task_id,
                        reason=summary,
                        affected=affected,
                        cascade=should_cascade,
                    )
                    return tx.ok(
                        Result(
                            success=True,
                            message=message,
                            data={
                                "task_id": task_id,
                                "outcome": "FAILED",
                                "affected_tasks": affected,
                                "cascade": should_cascade,
                            },
                        )
                    )

        except Exception as e:
            return Result(
                success=False, message=f"Operation failed: {e}", code=ErrorCode.INTERNAL_ERROR
            )
