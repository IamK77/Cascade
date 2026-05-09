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

"""Client mixin — read-only query operations."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from cascade.core.state import NodeState
from cascade.events import EventType
from cascade.replay import replay as replay_events
from cascade.types import ErrorCode, Result

if TYPE_CHECKING:
    from cascade.client.base import ClientBase


class QueryMixin:
    """Read-only queries: nodes, check, check_timeouts, history, show, diff, snapshot_at."""

    def nodes(
        self: ClientBase,
        *,
        state: str | None = None,
        include_pending_only: bool = False,
    ) -> Result:
        """List all tasks in the DAG."""
        try:
            with self._storage.lock():
                graph = self._load_or_recover()

                nodes_list: list[dict[str, Any]] = []
                by_state: dict[str, list[str]] = {}

                now = time.time()
                for nid, node in graph.nodes.items():
                    if state and node.state.name != state:
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

    def check(self: ClientBase, task_id: str) -> Result:
        """Check if a task claim is still valid (pull cancellation)."""
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

    def check_timeouts(self: ClientBase, default_timeout: float | None = None) -> Result:
        """Release stalled tasks that exceeded their timeout."""
        try:
            with self._mutate() as tx:
                now = time.time()
                released: list[dict[str, Any]] = []

                for node in tx.graph.nodes.values():
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
                    tx.emit(
                        EventType.TASK_TIMED_OUT,
                        node_id=node.id,
                        agent_id=old_agent,
                        elapsed=round(elapsed, 1),
                    )

                if released:
                    tx.save()

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
        self: ClientBase,
        *,
        node_id: str = "",
        event_type: str = "",
        last_n: int = 0,
        summary: bool = False,
    ) -> Result:
        """Query the event log."""
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

            if last_n > 0:
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
                if event.trace_id:
                    entry["trace_id"] = event.trace_id
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

    def show(self: ClientBase, logical_ts: int) -> Result:
        """Show the event at a specific logical timestamp."""
        try:
            event = self._storage.events.read_at(logical_ts)
            if event is None:
                return Result(
                    success=False,
                    message=f"No event at logical_ts={logical_ts}",
                    code=ErrorCode.TASK_NOT_FOUND,
                )

            ts = datetime.fromtimestamp(event.timestamp, tz=UTC).isoformat()
            data = dict(event.data)
            if "artifacts_ref" in data.get("context", {}):
                ref = data["context"]["artifacts_ref"]
                content = self._storage.content.get(ref)
                if content is not None:
                    data["context"]["artifacts_content"] = content

            result_data: dict[str, Any] = {
                "id": event.id,
                "type": event.type.value,
                "timestamp": ts,
                "logical_ts": event.logical_ts,
                "data": data,
            }
            if event.trace_id:
                result_data["trace_id"] = event.trace_id

            return Result(
                success=True,
                message=f"Event at logical_ts={logical_ts}",
                data=result_data,
            )

        except Exception as e:
            return Result(
                success=False, message=f"Failed to read event: {e}", code=ErrorCode.INTERNAL_ERROR
            )

    def diff(self: ClientBase, from_ts: int, to_ts: int) -> Result:
        """Show events between two logical timestamps (inclusive)."""
        if from_ts > to_ts:
            return Result(
                success=False,
                message=f"from_ts ({from_ts}) must be <= to_ts ({to_ts})",
                code=ErrorCode.INVALID_INPUT,
            )

        try:
            events = self._storage.events.read_range(from_ts, to_ts)

            formatted = []
            for event in events:
                ts = datetime.fromtimestamp(event.timestamp, tz=UTC).isoformat()
                entry: dict[str, Any] = {
                    "type": event.type.value,
                    "timestamp": ts,
                    "logical_ts": event.logical_ts,
                    "data": event.data,
                }
                if event.id:
                    entry["id"] = event.id
                if event.trace_id:
                    entry["trace_id"] = event.trace_id
                formatted.append(entry)

            nodes_changed: set[str] = set()
            for event in events:
                nid = event.data.get("node_id", "")
                if nid:
                    nodes_changed.add(nid)
                for nid in event.data.get("new_node_ids", []):
                    nodes_changed.add(nid)
                for nid in event.data.get("affected_nodes", []):
                    nodes_changed.add(nid)

            return Result(
                success=True,
                message=f"{len(formatted)} event(s) in range [{from_ts}, {to_ts}]",
                data={
                    "events": formatted,
                    "count": len(formatted),
                    "from_ts": from_ts,
                    "to_ts": to_ts,
                    "nodes_changed": sorted(nodes_changed),
                },
            )

        except Exception as e:
            return Result(
                success=False, message=f"Failed to read events: {e}", code=ErrorCode.INTERNAL_ERROR
            )

    def snapshot_at(self: ClientBase, logical_ts: int) -> Result:
        """Rebuild graph state at a specific logical timestamp."""
        try:
            events = self._storage.events.read_until(logical_ts)
            if not events:
                return Result(
                    success=False,
                    message=f"No events at or before logical_ts={logical_ts}",
                    code=ErrorCode.TASK_NOT_FOUND,
                )

            cascade = replay_events(events, self._storage.content)

            nodes_list: list[dict[str, Any]] = []
            for nid, node in cascade.nodes.items():
                node_info: dict[str, Any] = {
                    "id": nid,
                    "state": node.state.name,
                }
                if node.agent_id:
                    node_info["agent_id"] = node.agent_id
                nodes_list.append(node_info)

            return Result(
                success=True,
                message=f"Snapshot at logical_ts={logical_ts}: {len(nodes_list)} nodes",
                data={
                    "logical_ts": logical_ts,
                    "events_replayed": len(events),
                    "nodes": nodes_list,
                    "node_count": len(nodes_list),
                },
            )

        except Exception as e:
            return Result(
                success=False,
                message=f"Failed to build snapshot: {e}",
                code=ErrorCode.INTERNAL_ERROR,
            )
