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

"""Additional client tests targeting uncovered branches.

Focuses on: edit() state transitions, refine() cycle detection,
cascade failure recursion, claim() edge cases, and fencing token validation.
"""

from __future__ import annotations

from conftest import auto_deliverables, claim_token

from cascade.client import CascadeClient
from cascade.types import Contract, ErrorCode

# ── edit() state transitions ─────────────────────────────────────────


class TestEditStateTransition:
    def test_edit_invalid_state_name(self, client: CascadeClient):
        client.add("a")
        r = client.edit("a", state="NONEXISTENT")
        assert not r.success
        assert r.code == ErrorCode.INVALID_INPUT
        assert "Invalid state" in r.message

    def test_edit_invalid_transition(self, client: CascadeClient):
        client.add("a")
        r = client.edit("a", state="COMPLETED")
        assert not r.success
        assert r.code == ErrorCode.INVALID_INPUT
        assert "Invalid transition" in r.message

    def test_edit_valid_transition(self, client: CascadeClient):
        client.add("a")
        claim_token(client, "w1", "a")
        r = client.edit("a", state="COMPLETED")
        assert r.success

    def test_edit_completed_unblocks_dependents(self, client: CascadeClient):
        client.add("a")
        client.add("b", deps={"a": Contract("need", "promise")})
        claim_token(client, "w1", "a")
        r = client.edit("a", state="COMPLETED")
        assert r.success
        nodes = client.nodes(state="READY")
        ready_ids = [n["id"] for n in nodes.data.get("nodes", [])]
        assert "b" in ready_ids

    def test_edit_nonexistent_node(self, client: CascadeClient):
        r = client.edit("ghost", summary="test")
        assert not r.success
        assert r.code == ErrorCode.TASK_NOT_FOUND

    def test_edit_no_changes(self, client: CascadeClient):
        client.add("a")
        r = client.edit("a")
        assert r.success
        assert "No changes" in r.message

    def test_edit_state_case_insensitive(self, client: CascadeClient):
        client.add("a")
        claim_token(client, "w1", "a")
        r = client.edit("a", state="completed")
        assert r.success


# ── refine() cycle detection ─────────────────────────────────────────


class TestRefineCycleDetection:
    def test_refine_nonexistent_node(self, client: CascadeClient):
        client.add("a")
        r = client.refine("ghost", "a", expectation="E", promise="P")
        assert not r.success
        assert r.code == ErrorCode.TASK_NOT_FOUND

    def test_refine_nonexistent_dep(self, client: CascadeClient):
        client.add("a")
        r = client.refine("a", "ghost", expectation="E", promise="P")
        assert not r.success
        assert r.code == ErrorCode.DEP_NOT_FOUND

    def test_refine_duplicate_dependency(self, client: CascadeClient):
        client.add("a")
        client.add("b", deps={"a": Contract("E", "P")})
        r = client.refine("b", "a", expectation="E2", promise="P2")
        assert not r.success
        assert "already depends" in r.message

    def test_refine_would_create_cycle(self, client: CascadeClient):
        client.add("a")
        client.add("b", deps={"a": Contract("E1", "P1")})
        r = client.refine("a", "b", expectation="E2", promise="P2")
        assert not r.success
        assert "cycle" in r.message.lower()

    def test_refine_three_node_cycle(self, client: CascadeClient):
        client.add("a")
        client.add("b", deps={"a": Contract("E1", "P1")})
        client.add("c", deps={"b": Contract("E2", "P2")})
        r = client.refine("a", "c", expectation="E3", promise="P3")
        assert not r.success
        assert "cycle" in r.message.lower()

    def test_refine_valid_no_cycle(self, client: CascadeClient):
        client.add("a")
        client.add("b")
        client.add("c", deps={"a": Contract("E1", "P1")})
        r = client.refine("c", "b", expectation="E2", promise="P2")
        assert r.success


# ── cascade failure ──────────────────────────────────────────────────


class TestCascadeFailure:
    def test_cascade_fails_all_dependents(self, client: CascadeClient):
        client.add("a")
        client.add("b", deps={"a": Contract("E1", "P1")})
        client.add("c", deps={"b": Contract("E2", "P2")})
        _t = claim_token(client, "w1", "a")
        r = client.fail("a", cascade=True, reason="fatal", token=_t)
        assert r.success
        assert r.data.get("affected_count", 0) >= 3 or "cascaded" in r.message

        for nid in ("a", "b", "c"):
            nodes = client.nodes(state="FAILED")
            failed_ids = [n["id"] for n in nodes.data.get("nodes", [])]
            assert nid in failed_ids, f"{nid} should be FAILED"

    def test_cascade_skips_terminal_nodes(self, client: CascadeClient):
        """Already-completed nodes should not be cascaded to FAILED."""
        client.add("a")
        client.add("b", deps={"a": Contract("E1", "P1")})
        client.add("c", deps={"a": Contract("E2", "P2")})

        # Complete b's path first
        _t = claim_token(client, "w1", "a")
        client.complete(
            "a",
            summary="done",
            token=_t,
            deliverables=auto_deliverables(client, "a"),
        )
        _t2 = claim_token(client, "w2", "b")
        client.complete(
            "b",
            summary="done",
            token=_t2,
            deliverables=auto_deliverables(client, "b"),
        )

        # Now fail c with cascade — b should stay COMPLETED
        _t3 = claim_token(client, "w3", "c")
        r = client.fail("c", cascade=True, reason="fatal", token=_t3)
        assert r.success

        nodes_completed = client.nodes(state="COMPLETED")
        completed_ids = [n["id"] for n in nodes_completed.data.get("nodes", [])]
        assert "b" in completed_ids

    def test_cascade_fan_out(self, client: CascadeClient):
        """Cascade failure propagates to all branches of a fan-out."""
        client.add("root")
        client.add("left", deps={"root": Contract("E1", "P1")})
        client.add("right", deps={"root": Contract("E2", "P2")})
        _t = claim_token(client, "w1", "root")
        r = client.fail("root", cascade=True, reason="fatal", token=_t)
        assert r.success

        nodes_failed = client.nodes(state="FAILED")
        failed_ids = [n["id"] for n in nodes_failed.data.get("nodes", [])]
        assert "left" in failed_ids
        assert "right" in failed_ids

    def test_no_cascade_does_not_propagate(self, client: CascadeClient):
        client.add("a")
        client.add("b", deps={"a": Contract("E1", "P1")})
        _t = claim_token(client, "w1", "a")
        r = client.fail("a", cascade=False, reason="my fault", token=_t)
        assert r.success

        nodes_pending = client.nodes(state="PENDING")
        pending_ids = [n["id"] for n in nodes_pending.data.get("nodes", [])]
        assert "b" in pending_ids


# ── claim() edge cases ──────────────────────────────────────────────


class TestClaimEdgeCases:
    def test_claim_nonexistent_task(self, client: CascadeClient):
        r = client.claim("w1", "ghost")
        assert not r.success
        assert r.code == ErrorCode.TASK_NOT_FOUND

    def test_claim_task_held_by_another_agent(self, client: CascadeClient):
        client.add("a")
        client.claim("w1", "a")
        r = client.claim("w2", "a")
        assert not r.success
        assert r.code == ErrorCode.TASK_ALREADY_ACTIVE

    def test_claim_already_active_same_agent(self, client: CascadeClient):
        """Same agent re-claiming is blocked by the one-task-per-agent rule."""
        client.add("a")
        client.claim("w1", "a")
        r = client.claim("w1", "a")
        assert not r.success
        assert r.code == ErrorCode.ALREADY_HAS_ACTIVE

    def test_claim_terminal_task(self, client: CascadeClient):
        client.add("a")
        _t = claim_token(client, "w1", "a")
        client.complete("a", token=_t)
        r = client.claim("w2", "a")
        assert not r.success
        assert r.code == ErrorCode.TASK_TERMINAL

    def test_claim_pending_with_dep_count(self, client: CascadeClient):
        client.add("a")
        client.add("b", deps={"a": Contract("E", "P")})
        r = client.claim("w1", "b")
        assert not r.success
        assert r.code == ErrorCode.TASK_NOT_READY
        assert r.data.get("pending_dependencies", 0) > 0

    def test_auto_claim_no_ready_all_active(self, client: CascadeClient):
        client.add("a")
        client.claim("w1", "a")
        r = client.claim("w2")
        assert not r.success
        assert r.code == ErrorCode.NO_READY_TASKS
        assert r.data.get("active", 0) > 0

    def test_auto_claim_no_ready_all_pending(self, client: CascadeClient):
        client.add("a")
        client.add("b", deps={"a": Contract("E", "P")})
        client.claim("w1", "a")
        r = client.claim("w2")
        assert not r.success
        assert r.code == ErrorCode.NO_READY_TASKS


# ── fencing token validation ─────────────────────────────────────────


class TestFencingToken:
    def test_complete_without_token(self, client: CascadeClient):
        client.add("a")
        client.claim("w1", "a")
        r = client.complete("a", token=None)
        assert not r.success
        assert r.code == ErrorCode.STALE_TOKEN
        assert "token" in r.message.lower()

    def test_complete_stale_token(self, client: CascadeClient):
        client.add("a")
        _t = claim_token(client, "w1", "a")
        client.release("a", token=_t)
        # Graph epoch advanced, old token is stale
        client.claim("w2", "a")
        r = client.complete("a", token=_t)
        assert not r.success
        assert r.code == ErrorCode.STALE_TOKEN

    def test_complete_nonexistent_task(self, client: CascadeClient):
        client.add("a")
        _t = claim_token(client, "w1", "a")
        r = client.complete("ghost", token=_t)
        assert not r.success
        assert r.code == ErrorCode.TASK_NOT_FOUND

    def test_complete_not_active(self, client: CascadeClient):
        client.add("a")
        client.add("b", deps={"a": Contract("E", "P")})
        _t = claim_token(client, "w1", "a")
        # Try to complete b which is PENDING, using a's token
        r = client.complete("b", token=_t)
        assert not r.success
        assert r.code == ErrorCode.TASK_NOT_ACTIVE

    def test_complete_unaddressed_promises(self, client: CascadeClient):
        client.add("a")
        client.add("b", deps={"a": Contract("Need output", "Will deliver output")})
        _t = claim_token(client, "w1", "a")
        r = client.complete("a", summary="done", token=_t)
        assert not r.success
        assert r.code == ErrorCode.UNADDRESSED_PROMISES
