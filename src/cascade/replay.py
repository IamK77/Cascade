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

"""Event replay — rebuild graph state from the event log.

The event log is the source of truth. graph.json is a materialized
snapshot for fast access. This module can reconstruct the graph from
events alone, enabling:

- Disaster recovery (graph.json lost or corrupted)
- Distributed replication (follower replays leader's event stream)
- Consistency verification (replay == load)
"""

from collections.abc import Callable
from typing import Any

from cascade.core.cascade import Cascade
from cascade.core.node import Node
from cascade.core.state import NodeState
from cascade.events import Event, EventType
from cascade.types import Context


def replay(events: list[Event]) -> Cascade:
    """Rebuild a Cascade graph by replaying events in order.

    Events must be sorted by logical_ts (or insertion order).
    """
    cascade = Cascade()

    for event in events:
        _HANDLERS[event.type](cascade, event.data)

    return cascade


def verify(events: list[Event], snapshot: Cascade) -> list[str]:
    """Compare replayed state against a snapshot. Returns list of differences."""
    replayed = replay(events)
    diffs: list[str] = []

    replay_ids = set(replayed.nodes.keys())
    snap_ids = set(snapshot.nodes.keys())

    for nid in replay_ids - snap_ids:
        diffs.append(f"node {nid}: exists in replay but not in snapshot")
    for nid in snap_ids - replay_ids:
        diffs.append(f"node {nid}: exists in snapshot but not in replay")

    for nid in replay_ids & snap_ids:
        r_node = replayed.nodes[nid]
        s_node = snapshot.nodes[nid]
        if r_node.state != s_node.state:
            diffs.append(f"node {nid}: state {r_node.state} (replay) vs {s_node.state} (snapshot)")
        if r_node.agent_id != s_node.agent_id:
            diffs.append(
                f"node {nid}: agent {r_node.agent_id} (replay) vs {s_node.agent_id} (snapshot)"
            )

    for edge_key in replayed._contracts:
        if edge_key not in snapshot._contracts:
            diffs.append(f"edge {edge_key}: exists in replay but not in snapshot")
    for edge_key in snapshot._contracts:
        if edge_key not in replayed._contracts:
            diffs.append(f"edge {edge_key}: exists in snapshot but not in replay")

    return diffs


# ---------------------------------------------------------------------------
# Per-event-type handlers
# ---------------------------------------------------------------------------


def _handle_node_added(cascade: Cascade, data: dict[str, Any]) -> None:
    node_id = data["node_id"]
    if node_id in cascade.nodes:
        return
    cascade.add_node(Node(id=node_id))

    for dep in data.get("deps_contracts", []):
        dep_id = dep["node_id"]
        if dep_id in cascade.nodes:
            cascade.add_edge(
                dep_id,
                node_id,
                expectation=dep["expectation"],
                promise=dep["promise"],
            )

    for dep in data.get("dependent_contracts", []):
        dep_id = dep["node_id"]
        if dep_id in cascade.nodes:
            cascade.add_edge(
                node_id,
                dep_id,
                expectation=dep["expectation"],
                promise=dep["promise"],
            )


def _handle_node_removed(cascade: Cascade, data: dict[str, Any]) -> None:
    for nid in data.get("affected_nodes", []):
        if nid in cascade.nodes and cascade.nodes[nid].state != NodeState.ACTIVE:
            cascade.remove_node(nid)


def _handle_node_split(cascade: Cascade, data: dict[str, Any]) -> None:
    for nid in data.get("new_node_ids", []):
        if nid not in cascade.nodes:
            cascade.add_node(Node(id=nid))
    parent_id = data.get("node_id", "")
    if parent_id in cascade.nodes and cascade.nodes[parent_id].state != NodeState.ACTIVE:
        cascade.remove_node(parent_id)


def _handle_node_refined(cascade: Cascade, data: dict[str, Any]) -> None:
    node_id = data.get("node_id", "")
    dep_id = data.get("dependency_id", "")
    if node_id in cascade.nodes and dep_id in cascade.nodes:
        cascade.add_edge(
            dep_id,
            node_id,
            expectation=data.get("expectation", ""),
            promise=data.get("promise", ""),
        )


def _handle_node_edited(cascade: Cascade, data: dict[str, Any]) -> None:
    node_id = data.get("node_id", "")
    if node_id not in cascade.nodes:
        return
    node = cascade.nodes[node_id]

    new_state = data.get("new_state")
    if new_state and node.state.can_transition_to(NodeState[new_state]):
        node.update_state(NodeState[new_state])
        if NodeState[new_state] == NodeState.COMPLETED:
            cascade.notify_completion(node_id)

    ctx = data.get("context")
    if ctx:
        if node.context is None:
            node.context = Context()
        if "summary" in ctx:
            node.context.summary = ctx["summary"]
        if "critical" in ctx:
            node.context.critical.update(ctx["critical"])


def _handle_task_claimed(cascade: Cascade, data: dict[str, Any]) -> None:
    node_id = data.get("node_id", "")
    if node_id not in cascade.nodes:
        return
    node = cascade.nodes[node_id]
    if node.state == NodeState.READY:
        node.update_state(NodeState.ACTIVE)
    node.agent_id = data.get("agent_id")
    node.claimed_at = data.get("claimed_at")
    timeout = data.get("timeout")
    if timeout is not None:
        node.timeout = float(timeout)
    cascade.increment_epoch()


def _handle_task_completed(cascade: Cascade, data: dict[str, Any]) -> None:
    node_id = data.get("node_id", "")
    if node_id not in cascade.nodes:
        return
    node = cascade.nodes[node_id]
    if node.state == NodeState.ACTIVE:
        node.update_state(NodeState.COMPLETED)
    node.agent_id = None
    node.claimed_at = None
    node.timeout = None

    ctx = data.get("context")
    if ctx:
        if node.context is None:
            node.context = Context()
        if "summary" in ctx:
            node.context.summary = ctx["summary"]
        if "critical" in ctx:
            node.context.critical.update(ctx["critical"])
        if "artifacts" in ctx:
            node.context.artifacts = ctx["artifacts"]

    cascade.notify_completion(node_id)
    cascade.increment_epoch()


def _handle_task_failed(cascade: Cascade, data: dict[str, Any]) -> None:
    for nid in data.get("affected", [data.get("node_id", "")]):
        if nid in cascade.nodes:
            node = cascade.nodes[nid]
            if not node.state.is_terminal():
                node.update_state(NodeState.FAILED)
                node.agent_id = None
                node.claimed_at = None
                node.timeout = None
    cascade.increment_epoch()


def _handle_task_released(cascade: Cascade, data: dict[str, Any]) -> None:
    node_id = data.get("node_id", "")
    if node_id not in cascade.nodes:
        return
    node = cascade.nodes[node_id]
    if node.state == NodeState.ACTIVE:
        node.update_state(NodeState.READY)
    node.agent_id = None
    node.claimed_at = None
    node.timeout = None
    cascade.increment_epoch()


def _handle_task_timed_out(cascade: Cascade, data: dict[str, Any]) -> None:
    _handle_task_released(cascade, data)


def _handle_rework(cascade: Cascade, data: dict[str, Any]) -> None:
    corrective_id = data.get("corrective_node_id", "")
    if corrective_id and corrective_id not in cascade.nodes:
        cascade.add_node(Node(id=corrective_id))

    source_id = data.get("source_node_id", "")
    if source_id in cascade.nodes and corrective_id in cascade.nodes:
        source_contract = data.get("source_contract")
        if source_contract:
            cascade.add_edge(
                source_id,
                corrective_id,
                expectation=source_contract.get("expectation", ""),
                promise=source_contract.get("promise", ""),
            )

    requesting_id = data.get("requesting_node_id", "")
    if requesting_id in cascade.nodes and corrective_id in cascade.nodes:
        corrective_contract = data.get("corrective_contract")
        if corrective_contract:
            cascade.add_edge(
                corrective_id,
                requesting_id,
                expectation=corrective_contract.get("expectation", ""),
                promise=corrective_contract.get("promise", ""),
            )

    if requesting_id in cascade.nodes:
        node = cascade.nodes[requesting_id]
        if node.state == NodeState.ACTIVE:
            node.update_state(NodeState.PENDING)
            node.agent_id = None


def _handle_node_cancelled(cascade: Cascade, data: dict[str, Any]) -> None:
    node_id = data.get("node_id", "")
    if node_id in cascade.nodes:
        node = cascade.nodes[node_id]
        if not node.state.is_terminal():
            node.update_state(NodeState.CANCELLED)


def _noop(cascade: Cascade, data: dict[str, Any]) -> None:
    pass


_Handler = Callable[[Cascade, dict[str, Any]], None]

_HANDLERS: dict[EventType, _Handler] = {
    EventType.NODE_ADDED: _handle_node_added,
    EventType.NODE_REMOVED: _handle_node_removed,
    EventType.NODE_SPLIT: _handle_node_split,
    EventType.NODE_REFINED: _handle_node_refined,
    EventType.NODE_EDITED: _handle_node_edited,
    EventType.EDGE_ADDED: _noop,
    EventType.EDGE_REMOVED: _noop,
    EventType.TASK_CLAIMED: _handle_task_claimed,
    EventType.TASK_COMPLETED: _handle_task_completed,
    EventType.TASK_FAILED: _handle_task_failed,
    EventType.TASK_RELEASED: _handle_task_released,
    EventType.TASK_TIMED_OUT: _handle_task_timed_out,
    EventType.REWORK_REQUESTED: _handle_rework,
    EventType.NODE_CANCELLED: _handle_node_cancelled,
}
