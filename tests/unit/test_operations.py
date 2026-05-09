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

"""Tests for compound node operations (Split, Remove, Rework) and base class."""

from cascade.core.cascade import Cascade
from cascade.core.node import Node
from cascade.core.state import NodeState
from cascade.operations.base import NodeOperation, OperationResult
from cascade.operations.rework import ReworkOperation
from cascade.operations.split import SplitOperation
from cascade.types import Contract


def make_contracts(node_ids: list[str]) -> dict[str, Contract]:
    """Helper to create contracts for multiple nodes."""
    return {
        nid: Contract(expectation=f"Expect from {nid}", promise=f"Promise to {nid}")
        for nid in node_ids
    }


def _rework_graph() -> Cascade:
    """Build a -> b chain where a is COMPLETED and b is ACTIVE."""
    cascade = Cascade()
    cascade.add_node(Node(id="a"))
    cascade.add_node(Node(id="b"))
    cascade.add_edge("a", "b", expectation="E", promise="P")
    cascade.nodes["a"].state = NodeState.READY
    cascade.nodes["a"].update_state(NodeState.ACTIVE)
    cascade.nodes["a"].update_state(NodeState.COMPLETED)
    cascade.notify_completion("a")
    cascade.nodes["b"].update_state(NodeState.ACTIVE)
    cascade.nodes["b"].agent_id = "w1"
    return cascade


# ---------------------------------------------------------------------------
# OperationResult
# ---------------------------------------------------------------------------


class TestOperationResult:
    def test_success_repr(self):
        r = OperationResult(success=True, affected_nodes=["a", "b"])
        assert "Success" in repr(r)
        assert "nodes=2" in repr(r)

    def test_failure_repr(self):
        r = OperationResult(success=False, affected_nodes=[], message="err")
        assert "Failed" in repr(r)

    def test_data_defaults_to_none(self):
        r = OperationResult(success=True, affected_nodes=[])
        assert r.data is None

    def test_data_with_payload(self):
        r = OperationResult(success=True, affected_nodes=[], data={"key": "val"})
        assert r.data == {"key": "val"}


# ---------------------------------------------------------------------------
# NodeOperation base class validation
# ---------------------------------------------------------------------------


class TestBaseValidation:
    def test_validate_acyclic_graph(self):
        cascade = Cascade()
        cascade.add_node(Node(id="a"))
        cascade.add_node(Node(id="b"))
        cascade.add_edge("a", "b", expectation="E", promise="P")

        class DummyOp(NodeOperation):
            def execute(self):
                pass

        op = DummyOp(cascade)
        valid, error = op.validate()
        assert valid
        assert error is None

    def test_validate_node_exists(self):
        cascade = Cascade()
        cascade.add_node(Node(id="a"))

        class DummyOp(NodeOperation):
            def execute(self):
                pass

        op = DummyOp(cascade)
        valid, error = op._validate_node_exists("a")
        assert valid
        assert error is None

    def test_validate_node_not_exists(self):
        cascade = Cascade()

        class DummyOp(NodeOperation):
            def execute(self):
                pass

        op = DummyOp(cascade)
        valid, error = op._validate_node_exists("ghost")
        assert not valid
        assert "not found" in error

    def test_validate_nodes_exist_all_present(self):
        cascade = Cascade()
        cascade.add_node(Node(id="a"))
        cascade.add_node(Node(id="b"))

        class DummyOp(NodeOperation):
            def execute(self):
                pass

        op = DummyOp(cascade)
        valid, error = op._validate_nodes_exist(["a", "b"])
        assert valid

    def test_validate_nodes_exist_one_missing(self):
        cascade = Cascade()
        cascade.add_node(Node(id="a"))

        class DummyOp(NodeOperation):
            def execute(self):
                pass

        op = DummyOp(cascade)
        valid, error = op._validate_nodes_exist(["a", "ghost"])
        assert not valid
        assert "ghost" in error


# ---------------------------------------------------------------------------
# ReworkOperation
# ---------------------------------------------------------------------------


class TestReworkOperation:
    def test_rework_happy_path(self):
        cascade = _rework_graph()
        op = ReworkOperation(cascade)
        r = op.execute(
            requesting_node_id="b",
            source_node_id="a",
            corrective_node_id="a-fix",
            reason="output incomplete",
            source_contract=Contract("need correction", "will correct"),
            corrective_contract=Contract("need fix result", "will deliver fix"),
        )
        assert r.success
        assert "a-fix" in cascade.nodes
        assert cascade.nodes["b"].state == NodeState.PENDING
        assert cascade.nodes["a-fix"].state == NodeState.READY

    def test_rework_requesting_not_active(self):
        cascade = _rework_graph()
        cascade.nodes["b"].update_state(NodeState.READY)
        op = ReworkOperation(cascade)
        r = op.execute(
            requesting_node_id="b",
            source_node_id="a",
            corrective_node_id="a-fix",
            reason="test",
            source_contract=Contract("E", "P"),
            corrective_contract=Contract("E", "P"),
        )
        assert not r.success
        assert "ACTIVE" in r.message

    def test_rework_source_not_completed(self):
        cascade = Cascade()
        cascade.add_node(Node(id="a", state=NodeState.READY))
        cascade.add_node(Node(id="b", state=NodeState.ACTIVE))
        cascade.add_edge("a", "b", expectation="E", promise="P")
        op = ReworkOperation(cascade)
        r = op.execute(
            requesting_node_id="b",
            source_node_id="a",
            corrective_node_id="a-fix",
            reason="test",
            source_contract=Contract("E", "P"),
            corrective_contract=Contract("E", "P"),
        )
        assert not r.success
        assert "COMPLETED" in r.message

    def test_rework_requesting_node_not_found(self):
        cascade = _rework_graph()
        op = ReworkOperation(cascade)
        r = op.execute(
            requesting_node_id="ghost",
            source_node_id="a",
            corrective_node_id="a-fix",
            reason="test",
            source_contract=Contract("E", "P"),
            corrective_contract=Contract("E", "P"),
        )
        assert not r.success
        assert "not found" in r.message

    def test_rework_source_node_not_found(self):
        cascade = Cascade()
        cascade.add_node(Node(id="b", state=NodeState.ACTIVE))
        op = ReworkOperation(cascade)
        r = op.execute(
            requesting_node_id="b",
            source_node_id="ghost",
            corrective_node_id="fix",
            reason="test",
            source_contract=Contract("E", "P"),
            corrective_contract=Contract("E", "P"),
        )
        assert not r.success
        assert "not found" in r.message

    def test_rework_corrective_already_exists(self):
        cascade = _rework_graph()
        cascade.add_node(Node(id="existing"))
        op = ReworkOperation(cascade)
        r = op.execute(
            requesting_node_id="b",
            source_node_id="a",
            corrective_node_id="existing",
            reason="test",
            source_contract=Contract("E", "P"),
            corrective_contract=Contract("E", "P"),
        )
        assert not r.success
        assert "already exists" in r.message

    def test_rework_source_not_dependency_of_requester(self):
        cascade = Cascade()
        cascade.add_node(Node(id="a", state=NodeState.COMPLETED))
        cascade.add_node(Node(id="b", state=NodeState.ACTIVE))
        op = ReworkOperation(cascade)
        r = op.execute(
            requesting_node_id="b",
            source_node_id="a",
            corrective_node_id="fix",
            reason="test",
            source_contract=Contract("E", "P"),
            corrective_contract=Contract("E", "P"),
        )
        assert not r.success
        assert "not a dependency" in r.message

    def test_rework_creates_correct_edges(self):
        cascade = _rework_graph()
        op = ReworkOperation(cascade)
        op.execute(
            requesting_node_id="b",
            source_node_id="a",
            corrective_node_id="a-fix",
            reason="test",
            source_contract=Contract("E1", "P1"),
            corrective_contract=Contract("E2", "P2"),
        )
        assert ("a", "a-fix") in cascade.contracts
        assert ("a-fix", "b") in cascade.contracts
        assert cascade.contracts[("a", "a-fix")] == Contract("E1", "P1")
        assert cascade.contracts[("a-fix", "b")] == Contract("E2", "P2")

    def test_rework_corrective_has_provenance(self):
        cascade = _rework_graph()
        op = ReworkOperation(cascade)
        op.execute(
            requesting_node_id="b",
            source_node_id="a",
            corrective_node_id="a-fix",
            reason="output incomplete",
            source_contract=Contract("E", "P"),
            corrective_contract=Contract("E", "P"),
        )
        ctx = cascade.nodes["a-fix"].context
        assert ctx is not None
        assert ctx.provenance is not None
        assert ctx.provenance.rework_source == "a"
        assert ctx.provenance.rework_reason == "output incomplete"

    def test_rework_no_cycle_created(self):
        cascade = _rework_graph()
        op = ReworkOperation(cascade)
        op.execute(
            requesting_node_id="b",
            source_node_id="a",
            corrective_node_id="a-fix",
            reason="test",
            source_contract=Contract("E", "P"),
            corrective_contract=Contract("E", "P"),
        )
        assert not cascade.has_cycle()

    def test_rework_affected_nodes(self):
        cascade = _rework_graph()
        op = ReworkOperation(cascade)
        r = op.execute(
            requesting_node_id="b",
            source_node_id="a",
            corrective_node_id="a-fix",
            reason="test",
            source_contract=Contract("E", "P"),
            corrective_contract=Contract("E", "P"),
        )
        assert set(r.affected_nodes) == {"a", "b", "a-fix"}


class TestSplitOperation:
    def test_split_happy_path(self):
        cascade = Cascade()
        cascade.add_node(Node(id="parent"))
        op = SplitOperation(cascade)
        r = op.execute("parent", [Node(id="c1"), Node(id="c2")])
        assert r.success
        assert "parent" not in cascade.nodes
        assert "c1" in cascade.nodes
        assert "c2" in cascade.nodes
        assert r.data.parent_id == "parent"
        assert r.data.new_node_ids == ["c1", "c2"]

    def test_split_nonexistent_parent(self):
        cascade = Cascade()
        op = SplitOperation(cascade)
        r = op.execute("ghost", [Node(id="c1")])
        assert not r.success
        assert "not found" in r.message

    def test_split_child_already_exists(self):
        cascade = Cascade()
        cascade.add_node(Node(id="parent"))
        cascade.add_node(Node(id="existing"))
        op = SplitOperation(cascade)
        r = op.execute("parent", [Node(id="existing")])
        assert not r.success
        assert "already exists" in r.message

    def test_split_rewires_dependencies(self):
        """Parent's upstream edges should be re-wired to all children."""
        cascade = Cascade()
        cascade.add_node(Node(id="dep"))
        cascade.add_node(Node(id="parent"))
        cascade.add_edge("dep", "parent", expectation="E", promise="P")
        op = SplitOperation(cascade)
        r = op.execute("parent", [Node(id="c1"), Node(id="c2")])
        assert r.success
        assert ("dep", "c1") in cascade.contracts
        assert ("dep", "c2") in cascade.contracts

    def test_split_rewires_dependents(self):
        """Parent's downstream edges should be re-wired from all children."""
        cascade = Cascade()
        cascade.add_node(Node(id="parent"))
        cascade.add_node(Node(id="down"))
        cascade.add_edge("parent", "down", expectation="E", promise="P")
        op = SplitOperation(cascade)
        r = op.execute("parent", [Node(id="c1"), Node(id="c2")])
        assert r.success
        assert ("c1", "down") in cascade.contracts
        assert ("c2", "down") in cascade.contracts

    def test_split_preserves_contracts(self):
        """Re-wired edges should carry the original contracts."""
        cascade = Cascade()
        cascade.add_node(Node(id="dep"))
        cascade.add_node(Node(id="parent"))
        cascade.add_edge("dep", "parent", expectation="need spec", promise="deliver spec")
        op = SplitOperation(cascade)
        op.execute("parent", [Node(id="c1")])
        c = cascade.get_contract("dep", "c1")
        assert c is not None
        assert c.expectation == "need spec"
        assert c.promise == "deliver spec"

    def test_split_no_cycle(self):
        """Split should never create a cycle."""
        cascade = Cascade()
        cascade.add_node(Node(id="a"))
        cascade.add_node(Node(id="parent"))
        cascade.add_node(Node(id="z"))
        cascade.add_edge("a", "parent", expectation="E1", promise="P1")
        cascade.add_edge("parent", "z", expectation="E2", promise="P2")
        op = SplitOperation(cascade)
        op.execute("parent", [Node(id="c1"), Node(id="c2")])
        assert not cascade.has_cycle()

    def test_split_children_readiness(self):
        """After split, children with met deps should be READY."""
        cascade = Cascade()
        cascade.add_node(Node(id="dep", state=NodeState.COMPLETED))
        cascade.add_node(Node(id="parent"))
        cascade.add_edge("dep", "parent", expectation="E", promise="P")
        cascade.notify_completion("dep")
        op = SplitOperation(cascade)
        op.execute("parent", [Node(id="c1")])
        assert cascade.nodes["c1"].state == NodeState.READY

    def test_split_shared_promises_tip(self):
        """When multiple children inherit same downstream, message should hint."""
        cascade = Cascade()
        cascade.add_node(Node(id="parent"))
        cascade.add_node(Node(id="down"))
        cascade.add_edge("parent", "down", expectation="E", promise="P")
        op = SplitOperation(cascade)
        r = op.execute("parent", [Node(id="c1"), Node(id="c2")])
        assert r.success
        assert "Tip" in r.message or "differentiate" in r.message

    def test_split_alias_method(self):
        """split() should behave identically to execute()."""
        cascade = Cascade()
        cascade.add_node(Node(id="parent"))
        op = SplitOperation(cascade)
        r = op.split("parent", [Node(id="c1")])
        assert r.success
