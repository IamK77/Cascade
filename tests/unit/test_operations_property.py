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

"""Property-based tests for operations/rework.py and operations/split.py.

Invariants tested:
- Rework: DAG acyclic, forward-only growth, requester goes PENDING
- Split: DAG acyclic, edges re-wired correctly, readiness consistent
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from cascade.core.cascade import Cascade
from cascade.core.node import Node
from cascade.core.state import NodeState
from cascade.operations.rework import ReworkOperation
from cascade.operations.split import SplitOperation
from cascade.types import Contract


def _chain(n: int) -> Cascade:
    """Build a linear chain: n0 -> n1 -> ... -> n(n-1), all READY."""
    cascade = Cascade()
    for i in range(n):
        cascade.add_node(Node(id=f"n{i}"))
    for i in range(n - 1):
        cascade.add_edge(f"n{i}", f"n{i + 1}", expectation="E", promise=f"P{i}")
    return cascade


# ---------------------------------------------------------------------------
# Rework invariants
# ---------------------------------------------------------------------------


class TestReworkInvariants:
    @given(
        chain_len=st.integers(min_value=2, max_value=6),
        data=st.data(),
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_rework_never_creates_cycle(self, chain_len, data):
        """Rework on any valid source-requester pair must keep DAG acyclic."""
        cascade = _chain(chain_len)

        source_idx = data.draw(st.integers(min_value=0, max_value=chain_len - 2))
        req_idx = data.draw(st.integers(min_value=source_idx + 1, max_value=chain_len - 1))

        source_id = f"n{source_idx}"
        req_id = f"n{req_idx}"

        cascade.nodes[source_id].state = NodeState.READY
        cascade.nodes[source_id].update_state(NodeState.ACTIVE)
        cascade.nodes[source_id].update_state(NodeState.COMPLETED)
        cascade.notify_completion(source_id)

        for i in range(source_idx + 1, req_idx + 1):
            nid = f"n{i}"
            if cascade.nodes[nid].state == NodeState.READY:
                cascade.nodes[nid].update_state(NodeState.ACTIVE)
                if i < req_idx:
                    cascade.nodes[nid].update_state(NodeState.COMPLETED)
                    cascade.notify_completion(nid)

        if cascade.nodes[req_id].state != NodeState.ACTIVE:
            return

        op = ReworkOperation(cascade)
        corrective_id = f"fix-{source_id}-{req_id}"
        r = op.execute(
            requesting_node_id=req_id,
            source_node_id=source_id,
            corrective_node_id=corrective_id,
            reason="test",
            source_contract=Contract("E", "P"),
            corrective_contract=Contract("E", "P"),
        )

        if r.success:
            assert not cascade.has_cycle(), (
                f"Rework created cycle: source={source_id}, req={req_id}"
            )

    @given(
        chain_len=st.integers(min_value=2, max_value=5),
    )
    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
    def test_rework_requester_always_pending_after_success(self, chain_len):
        """After successful rework, requester must be PENDING (new unmet dep)."""
        cascade = _chain(chain_len)
        source_id = "n0"
        req_id = f"n{chain_len - 1}"

        cascade.nodes[source_id].state = NodeState.READY
        cascade.nodes[source_id].update_state(NodeState.ACTIVE)
        cascade.nodes[source_id].update_state(NodeState.COMPLETED)
        cascade.notify_completion(source_id)

        for i in range(1, chain_len):
            nid = f"n{i}"
            if cascade.nodes[nid].state == NodeState.READY:
                cascade.nodes[nid].update_state(NodeState.ACTIVE)
                if i < chain_len - 1:
                    cascade.nodes[nid].update_state(NodeState.COMPLETED)
                    cascade.notify_completion(nid)

        if cascade.nodes[req_id].state != NodeState.ACTIVE:
            return

        op = ReworkOperation(cascade)
        r = op.execute(
            requesting_node_id=req_id,
            source_node_id=source_id,
            corrective_node_id="fix",
            reason="test",
            source_contract=Contract("E", "P"),
            corrective_contract=Contract("E", "P"),
        )

        if r.success:
            assert cascade.nodes[req_id].state == NodeState.PENDING, (
                f"Requester should be PENDING after rework, got {cascade.nodes[req_id].state}"
            )

    @given(
        chain_len=st.integers(min_value=2, max_value=5),
    )
    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
    def test_rework_corrective_is_ready(self, chain_len):
        """After successful rework, corrective node should be READY
        (its only dep is the COMPLETED source)."""
        cascade = _chain(chain_len)
        source_id = "n0"
        req_id = f"n{chain_len - 1}"

        cascade.nodes[source_id].state = NodeState.READY
        cascade.nodes[source_id].update_state(NodeState.ACTIVE)
        cascade.nodes[source_id].update_state(NodeState.COMPLETED)
        cascade.notify_completion(source_id)

        for i in range(1, chain_len):
            nid = f"n{i}"
            if cascade.nodes[nid].state == NodeState.READY:
                cascade.nodes[nid].update_state(NodeState.ACTIVE)
                if i < chain_len - 1:
                    cascade.nodes[nid].update_state(NodeState.COMPLETED)
                    cascade.notify_completion(nid)

        if cascade.nodes[req_id].state != NodeState.ACTIVE:
            return

        op = ReworkOperation(cascade)
        r = op.execute(
            requesting_node_id=req_id,
            source_node_id=source_id,
            corrective_node_id="fix",
            reason="test",
            source_contract=Contract("E", "P"),
            corrective_contract=Contract("E", "P"),
        )

        if r.success:
            assert cascade.nodes["fix"].state == NodeState.READY, (
                f"Corrective should be READY, got {cascade.nodes['fix'].state}"
            )


# ---------------------------------------------------------------------------
# Split invariants
# ---------------------------------------------------------------------------


class TestSplitInvariants:
    @given(
        n_children=st.integers(min_value=1, max_value=5),
        has_upstream=st.booleans(),
        has_downstream=st.booleans(),
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_split_never_creates_cycle(self, n_children, has_upstream, has_downstream):
        """Split with any number of children, optional upstream/downstream, stays acyclic."""
        cascade = Cascade()
        cascade.add_node(Node(id="parent"))

        if has_upstream:
            cascade.add_node(Node(id="up"))
            cascade.add_edge("up", "parent", expectation="E", promise="P")

        if has_downstream:
            cascade.add_node(Node(id="down"))
            cascade.add_edge("parent", "down", expectation="E", promise="P")

        children = [Node(id=f"c{i}") for i in range(n_children)]
        op = SplitOperation(cascade)
        r = op.execute("parent", children)

        if r.success:
            assert not cascade.has_cycle()

    @given(
        n_children=st.integers(min_value=1, max_value=4),
    )
    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
    def test_split_upstream_edges_rewired_to_all_children(self, n_children):
        """Every child must have an edge from every original upstream node."""
        cascade = Cascade()
        cascade.add_node(Node(id="up1"))
        cascade.add_node(Node(id="up2"))
        cascade.add_node(Node(id="parent"))
        cascade.add_edge("up1", "parent", expectation="E1", promise="P1")
        cascade.add_edge("up2", "parent", expectation="E2", promise="P2")

        children = [Node(id=f"c{i}") for i in range(n_children)]
        op = SplitOperation(cascade)
        r = op.execute("parent", children)

        assert r.success
        for i in range(n_children):
            assert ("up1", f"c{i}") in cascade.contracts
            assert ("up2", f"c{i}") in cascade.contracts

    @given(
        n_children=st.integers(min_value=1, max_value=4),
    )
    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
    def test_split_readiness_consistent(self, n_children):
        """After split, every non-terminal node's readiness matches deps."""
        cascade = Cascade()
        cascade.add_node(Node(id="up", state=NodeState.COMPLETED))
        cascade.add_node(Node(id="parent"))
        cascade.add_edge("up", "parent", expectation="E", promise="P")
        cascade.notify_completion("up")

        children = [Node(id=f"c{i}") for i in range(n_children)]
        op = SplitOperation(cascade)
        r = op.execute("parent", children)

        assert r.success
        for nid, node in cascade.nodes.items():
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
                    f"{nid}: 0 pending deps but state is {node.state}"
                )
            else:
                assert node.state == NodeState.PENDING, (
                    f"{nid}: {pending} pending deps but state is {node.state}"
                )
