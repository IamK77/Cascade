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

"""Tests for the rework mechanism -- upstream feedback via forward derivation."""

from conftest import auto_deliverables, claim_token

from cascade.client import CascadeClient, Contract
from cascade.core.cascade import Cascade
from cascade.core.node import Node
from cascade.core.state import NodeState
from cascade.operations.rework import ReworkOperation
from cascade.types import Context


class TestReworkOperation:
    """Tests for ReworkOperation at the operation level."""

    def _build_a_to_b(self) -> Cascade:
        """Build a simple A -> B graph where A is completed and B is active."""
        cascade = Cascade()
        cascade.add_node(
            Node(
                id="A",
                state=NodeState.READY,
                context=Context(
                    critical={"result": "wrong analysis"},
                    summary="Original analysis output",
                ),
            )
        )
        cascade.add_node(Node(id="B", state=NodeState.PENDING))
        cascade.add_edge("A", "B", expectation="Expect analysis", promise="Provide analysis")

        # Complete A, activate B
        cascade.nodes["A"].update_state(NodeState.ACTIVE)
        cascade.nodes["A"].update_state(NodeState.COMPLETED)
        cascade.notify_completion("A")
        cascade.nodes["B"].update_state(NodeState.ACTIVE)
        cascade.nodes["B"].agent_id = "agent-1"

        return cascade

    def test_basic_rework(self):
        """Test that rework creates a corrective node and rewires the graph."""
        cascade = self._build_a_to_b()

        op = ReworkOperation(cascade)
        result = op.execute(
            requesting_node_id="B",
            source_node_id="A",
            corrective_node_id="A_fix",
            reason="Analysis missed critical edge case X",
            source_contract=Contract(
                expectation="Original analysis to review",
                promise="A's original output",
            ),
            corrective_contract=Contract(
                expectation="Revised analysis addressing edge case X",
                promise="Corrected analysis",
            ),
        )

        assert result.success
        assert result.data is not None
        assert result.data.corrective_node_id == "A_fix"

        # Corrective node exists and is READY (depends on completed A)
        assert "A_fix" in cascade.nodes
        assert cascade.nodes["A_fix"].state == NodeState.READY

        # Corrective node has feedback as context
        assert cascade.nodes["A_fix"].context is not None
        assert "edge case X" in cascade.nodes["A_fix"].context.summary
        assert cascade.nodes["A_fix"].context.critical["rework_source"] == "A"

        # Corrective node depends on A (can see original output)
        deps = [d.id for d in cascade.get_dependencies("A_fix")]
        assert "A" in deps

        # B now depends on A_fix (in addition to A)
        assert cascade.has_dependency("B", "A_fix")

        # B is PENDING (waiting for A_fix to complete)
        assert cascade.nodes["B"].state == NodeState.PENDING
        assert cascade.pending_dependency_count("B") == 1  # only A_fix (A is completed)

    def test_rework_then_complete(self):
        """Test full cycle: rework requested, corrective work done, requester resumes."""
        cascade = self._build_a_to_b()

        # B requests rework
        op = ReworkOperation(cascade)
        op.execute(
            requesting_node_id="B",
            source_node_id="A",
            corrective_node_id="A_fix",
            reason="Wrong data",
            source_contract=Contract(expectation="E", promise="P"),
            corrective_contract=Contract(expectation="E2", promise="P2"),
        )

        # Another agent picks up A_fix and completes it
        cascade.nodes["A_fix"].update_state(NodeState.ACTIVE)
        cascade.nodes["A_fix"].agent_id = "agent-2"
        cascade.nodes["A_fix"].update_state(NodeState.COMPLETED)
        unblocked = cascade.notify_completion("A_fix")

        # B should be unblocked
        assert "B" in unblocked
        assert cascade.nodes["B"].state == NodeState.READY

    def test_rework_requires_active_requester(self):
        """Rework can only be requested by an ACTIVE node."""
        cascade = Cascade()
        cascade.add_node(Node(id="A", state=NodeState.COMPLETED))
        cascade.add_node(Node(id="B", state=NodeState.READY))
        cascade.add_edge("A", "B", expectation="E", promise="P")

        op = ReworkOperation(cascade)
        result = op.execute(
            requesting_node_id="B",
            source_node_id="A",
            corrective_node_id="A_fix",
            reason="Wrong",
            source_contract=Contract(expectation="E", promise="P"),
            corrective_contract=Contract(expectation="E2", promise="P2"),
        )

        assert not result.success
        assert "ACTIVE" in result.message

    def test_rework_requires_completed_source(self):
        """Rework can only target a COMPLETED source node."""
        cascade = Cascade()
        cascade.add_node(Node(id="A", state=NodeState.ACTIVE))
        cascade.add_node(Node(id="B", state=NodeState.ACTIVE))
        cascade.add_edge("A", "B", expectation="E", promise="P")

        op = ReworkOperation(cascade)
        result = op.execute(
            requesting_node_id="B",
            source_node_id="A",
            corrective_node_id="A_fix",
            reason="Wrong",
            source_contract=Contract(expectation="E", promise="P"),
            corrective_contract=Contract(expectation="E2", promise="P2"),
        )

        assert not result.success
        assert "COMPLETED" in result.message

    def test_rework_requires_dependency_relationship(self):
        """Source must be an actual dependency of the requester."""
        cascade = Cascade()
        cascade.add_node(Node(id="A", state=NodeState.COMPLETED))
        cascade.add_node(Node(id="B", state=NodeState.COMPLETED))
        cascade.add_node(Node(id="C", state=NodeState.ACTIVE))
        cascade.add_edge("A", "C", expectation="E", promise="P")
        # B is completed but NOT a dependency of C

        op = ReworkOperation(cascade)
        result = op.execute(
            requesting_node_id="C",
            source_node_id="B",
            corrective_node_id="B_fix",
            reason="Wrong",
            source_contract=Contract(expectation="E", promise="P"),
            corrective_contract=Contract(expectation="E2", promise="P2"),
        )

        assert not result.success
        assert "not a dependency" in result.message

    def test_rework_preserves_dag(self):
        """Rework must not create cycles."""
        cascade = self._build_a_to_b()

        op = ReworkOperation(cascade)
        op.execute(
            requesting_node_id="B",
            source_node_id="A",
            corrective_node_id="A_fix",
            reason="Wrong",
            source_contract=Contract(expectation="E", promise="P"),
            corrective_contract=Contract(expectation="E2", promise="P2"),
        )

        assert not cascade.has_cycle()
        # Topological sort should work
        order = cascade.topological_sort()
        assert order.index("A") < order.index("A_fix")
        assert order.index("A_fix") < order.index("B")


class TestReworkTool:
    """Tests for rework via CascadeClient (full integration with storage)."""

    def test_rework_via_client(self, client: CascadeClient, temp_storage):
        """Test rework through the client interface."""
        # Build graph: root -> task_b
        client.add("root")
        client.add(
            "task_b",
            deps={"root": Contract("Expect output from root", "Promise output to dependent")},
        )

        # Complete root
        _t = claim_token(client, "agent-1", "root")
        client.complete("root", token=_t, deliverables=auto_deliverables(client, "root"))

        # Agent 2 picks up task_b
        client.claim("agent-2", "task_b")

        # Agent 2 discovers root's output is wrong, requests rework
        result = client.rework(
            source="root",
            corrective="root_fix",
            reason="Root analysis missed edge case",
            agent_id="agent-2",
            source_expectation="Original analysis to review",
            source_promise="Root's original output",
            corrective_expectation="Revised analysis",
            corrective_promise="Corrected analysis",
        )

        assert result.success is True
        assert result.data["corrective_node_id"] == "root_fix"

        # Verify graph state
        with temp_storage.lock():
            cascade = temp_storage.load()

            # root_fix exists and is READY
            assert "root_fix" in cascade.nodes
            assert cascade.nodes["root_fix"].state == NodeState.READY

            # task_b is PENDING (waiting for root_fix)
            assert cascade.nodes["task_b"].state == NodeState.PENDING
            assert cascade.nodes["task_b"].agent_id is None

            # task_b depends on root_fix
            assert cascade.has_dependency("task_b", "root_fix")

            # DAG is valid
            assert not cascade.has_cycle()

    def test_rework_missing_params(self, client: CascadeClient):
        """Test that rework validates required params."""
        result = client.rework(
            source="",
            corrective="",
            reason="",
            agent_id="",
            source_expectation="",
            source_promise="",
            corrective_expectation="",
            corrective_promise="",
        )
        assert not result.success
        assert "Missing required" in result.message

    def test_rework_no_active_task(self, client: CascadeClient):
        """Test rework fails if agent has no active task."""
        client.add("root")

        result = client.rework(
            source="root",
            corrective="root_fix",
            reason="Wrong",
            agent_id="agent-no-task",
            source_expectation="E",
            source_promise="P",
            corrective_expectation="E2",
            corrective_promise="P2",
        )

        assert not result.success
        assert "no active task" in result.message
