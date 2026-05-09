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

"""Property-based tests for Cascade invariants.

Uses Hypothesis to generate random operation sequences and verify
that system invariants hold regardless of the specific sequence.
These tests are designed to find bugs, not to increase coverage.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from cascade.client import CascadeClient
from cascade.core.cascade import Cascade
from cascade.core.node import Node
from cascade.core.state import NodeState
from cascade.events import EventType
from cascade.replay import verify
from cascade.storage.file_storage import FileStorage
from cascade.types import Contract

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

node_ids = st.text(
    alphabet=st.characters(categories=("L", "N"), min_codepoint=ord("a"), max_codepoint=ord("z")),
    min_size=1,
    max_size=4,
)

contract_text = st.text(min_size=1, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz ")


# ---------------------------------------------------------------------------
# Invariant 1: Graph is always acyclic
# ---------------------------------------------------------------------------


class TestAcyclicInvariant:
    @given(
        data=st.data(),
        n_nodes=st.integers(min_value=2, max_value=8),
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_no_cycles_after_random_edges(self, data, n_nodes):
        """Adding random edges via add_edge (with cycle check) never creates a cycle."""
        cascade = Cascade()
        ids = [f"n{i}" for i in range(n_nodes)]
        for nid in ids:
            cascade.add_node(Node(id=nid))

        for _ in range(n_nodes * 2):
            from_id = data.draw(st.sampled_from(ids))
            to_id = data.draw(st.sampled_from(ids))
            if from_id == to_id:
                continue
            if cascade._has_path(to_id, from_id):
                continue
            if (from_id, to_id) in cascade.contracts:
                continue
            cascade.add_edge(from_id, to_id, expectation="E", promise="P")

        assert not cascade.has_cycle(), "Graph has a cycle after edge additions"


# ---------------------------------------------------------------------------
# Invariant 2: Readiness is always consistent with dependencies
# ---------------------------------------------------------------------------


class TestReadinessInvariant:
    @given(
        data=st.data(),
        n_nodes=st.integers(min_value=2, max_value=6),
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_readiness_matches_dependencies(self, data, n_nodes):
        """A non-terminal, non-ACTIVE node's readiness must match its dependency state."""
        cascade = Cascade()
        ids = [f"n{i}" for i in range(n_nodes)]
        for nid in ids:
            cascade.add_node(Node(id=nid))

        for i in range(1, n_nodes):
            if data.draw(st.booleans()):
                from_id = ids[data.draw(st.integers(min_value=0, max_value=i - 1))]
                cascade.add_edge(from_id, ids[i], expectation="E", promise="P")

        for nid in ids:
            if data.draw(st.booleans()):
                node = cascade.nodes[nid]
                if node.state == NodeState.READY:
                    node.update_state(NodeState.ACTIVE)
                    if data.draw(st.booleans()):
                        node.update_state(NodeState.COMPLETED)
                        cascade.notify_completion(nid)

        for nid in ids:
            node = cascade.nodes[nid]
            if node.state in (
                NodeState.ACTIVE,
                NodeState.COMPLETED,
                NodeState.FAILED,
                NodeState.CANCELLED,
            ):
                continue
            pending = cascade.pending_dependency_count(nid)
            if pending == 0:
                assert node.state == NodeState.READY, (
                    f"Node {nid} has 0 pending deps but is {node.state}"
                )
            else:
                assert node.state == NodeState.PENDING, (
                    f"Node {nid} has {pending} pending deps but is {node.state}"
                )


# ---------------------------------------------------------------------------
# Invariant 3: Terminal nodes have no agent state
# ---------------------------------------------------------------------------


class TestTerminalNodeInvariant:
    @given(data=st.data())
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_terminal_nodes_have_no_agent(self, data):
        """COMPLETED/FAILED nodes via client should have agent_id/claimed_at/timeout cleared."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = CascadeClient(FileStorage(Path(tmpdir)))
            client.add("a")
            client.add("b")

            for nid in ("a", "b"):
                r = client.claim("w1", nid)
                if not r.success:
                    continue
                token = r.data.get("token")

                action = data.draw(st.sampled_from(["complete", "fail", "release"]))
                if action == "complete":
                    client.complete(nid, token=token)
                elif action == "fail":
                    client.fail(nid, token=token, reason="test")
                else:
                    client.release(nid, token=token)

            with client.storage.lock():
                graph = client.storage.load()
            if graph is None:
                return
            for node in graph.nodes.values():
                if node.state.is_terminal():
                    assert node.agent_id is None, (
                        f"Terminal node {node.id} ({node.state}) has agent_id={node.agent_id}"
                    )
                    assert node.claimed_at is None, (
                        f"Terminal node {node.id} ({node.state}) has claimed_at set"
                    )
                    assert node.timeout is None, (
                        f"Terminal node {node.id} ({node.state}) has timeout set"
                    )


# ---------------------------------------------------------------------------
# Invariant 4: Replay == Direct operations (cross-validation)
# ---------------------------------------------------------------------------


class TestReplayConsistency:
    def test_add_claim_complete_replay_matches(self):
        """Replay of events from a simple workflow must match the final graph state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = FileStorage(Path(tmpdir))
            client = CascadeClient(storage)

            client.add("a")
            client.add("b", deps={"a": Contract("need", "deliver")})
            r = client.claim("w1", "a")
            token = r.data["token"]
            client.complete("a", token=token, summary="done", deliverables={"b": "output"})

            with storage.lock():
                snapshot = storage.load()
            events = list(storage.events.read_all())
            diffs = verify(events, snapshot)
            assert diffs == [], f"Replay diverged from snapshot: {diffs}"

    @given(
        data=st.data(),
        n_nodes=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_random_workflow_replay_matches(self, data, n_nodes):
        """Random add/claim/complete/fail/release sequences must replay consistently."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = FileStorage(Path(tmpdir))
            client = CascadeClient(storage)

            ids = [f"n{i}" for i in range(n_nodes)]
            for nid in ids:
                client.add(nid)

            for _ in range(n_nodes * 2):
                nid = data.draw(st.sampled_from(ids))
                action = data.draw(st.sampled_from(["claim", "complete", "fail", "release"]))

                if action == "claim":
                    client.claim(f"agent-{nid}", nid)
                elif action in ("complete", "fail", "release"):
                    with storage.lock():
                        graph = storage.load()
                    if graph is None:
                        continue
                    node = graph.nodes.get(nid)
                    if node is None or node.state != NodeState.ACTIVE:
                        continue
                    token = graph.epoch
                    if action == "complete":
                        client.complete(nid, token=token)
                    elif action == "fail":
                        client.fail(nid, token=token, reason="test")
                    else:
                        client.release(nid, token=token)

            with storage.lock():
                snapshot = storage.load()
            if snapshot is None:
                return
            events = list(storage.events.read_all())
            diffs = verify(events, snapshot)
            assert diffs == [], f"Replay diverged: {diffs}"


# ---------------------------------------------------------------------------
# Invariant 5: Cascade failure reaches all non-terminal dependents
# ---------------------------------------------------------------------------


class TestCascadeFailureInvariant:
    @given(
        data=st.data(),
        depth=st.integers(min_value=2, max_value=5),
        width=st.integers(min_value=1, max_value=3),
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_cascade_failure_reaches_all(self, data, depth, width):
        """Cascade failure from root must fail all reachable non-terminal nodes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            client = CascadeClient(FileStorage(Path(tmpdir)))

            prev_layer = ["root"]
            client.add("root")

            for d in range(1, depth):
                layer = []
                for w in range(width):
                    nid = f"d{d}w{w}"
                    parent = data.draw(st.sampled_from(prev_layer))
                    client.add(nid, deps={parent: Contract("E", "P")})
                    layer.append(nid)
                prev_layer = layer

            r = client.claim("w1", "root")
            assert r.success
            token = r.data["token"]
            r = client.fail("root", cascade=True, reason="fatal", token=token)
            assert r.success

            nodes_r = client.nodes()
            for node_info in nodes_r.data.get("nodes", []):
                assert node_info["state"] == "FAILED", (
                    f"Node {node_info['id']} is {node_info['state']}, expected FAILED"
                )


# ---------------------------------------------------------------------------
# Invariant 6: State machine transitions are always valid
# ---------------------------------------------------------------------------


class TestStateTransitionInvariant:
    @given(
        data=st.data(),
        n_ops=st.integers(min_value=3, max_value=10),
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_all_event_transitions_are_valid(self, data, n_ops):
        """Every state change recorded in events must be a valid state machine transition."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = FileStorage(Path(tmpdir))
            client = CascadeClient(storage)

            client.add("a")
            client.add("b")

            for _ in range(n_ops):
                nid = data.draw(st.sampled_from(["a", "b"]))
                action = data.draw(st.sampled_from(["claim", "complete", "fail", "release"]))
                if action == "claim":
                    client.claim(f"agent-{nid}", nid)
                else:
                    with storage.lock():
                        graph = storage.load()
                    if graph is None:
                        continue
                    node = graph.nodes.get(nid)
                    if node is None or node.state != NodeState.ACTIVE:
                        continue
                    token = graph.epoch
                    if action == "complete":
                        client.complete(nid, token=token)
                    elif action == "fail":
                        client.fail(nid, token=token, reason="r")
                    else:
                        client.release(nid, token=token)

            events = list(storage.events.read_all())
            state: dict[str, NodeState] = {}
            for event in events:
                nid = event.data.get("node_id", "")
                if event.type == EventType.NODE_ADDED:
                    state[nid] = NodeState.READY
                elif event.type == EventType.TASK_CLAIMED:
                    if nid in state:
                        assert state[nid].can_transition_to(NodeState.ACTIVE), (
                            f"Invalid transition: {state[nid]} -> ACTIVE for {nid}"
                        )
                        state[nid] = NodeState.ACTIVE
                elif event.type == EventType.TASK_COMPLETED:
                    if nid in state:
                        assert state[nid].can_transition_to(NodeState.COMPLETED), (
                            f"Invalid transition: {state[nid]} -> COMPLETED for {nid}"
                        )
                        state[nid] = NodeState.COMPLETED
                elif event.type == EventType.TASK_FAILED:
                    affected = event.data.get("affected", [nid])
                    for aid in affected:
                        if aid in state:
                            assert state[aid].can_transition_to(NodeState.FAILED), (
                                f"Invalid transition: {state[aid]} -> FAILED for {aid}"
                            )
                            state[aid] = NodeState.FAILED
                elif event.type == EventType.TASK_RELEASED:
                    if nid in state:
                        assert state[nid].can_transition_to(NodeState.READY), (
                            f"Invalid transition: {state[nid]} -> READY for {nid}"
                        )
                        state[nid] = NodeState.READY
