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

"""Comprehensive tests for the CascadeClient typed API."""

from __future__ import annotations

import pytest
from conftest import claim_token

from cascade.client import CascadeClient
from cascade.types import Contract, NodeInfo, Result, TaskView


@pytest.fixture
def client(temp_storage):
    """Create a CascadeClient backed by temp storage."""
    return CascadeClient(temp_storage.base_dir)


def _nodes(client: CascadeClient, **kwargs) -> list[NodeInfo]:
    """Helper: project nodes() Result into list[NodeInfo]."""
    return NodeInfo.list_from_result(client.nodes(**kwargs))


# ── add() ──────────────────────────────────────────────────────────────


class TestAdd:
    def test_add_simple(self, client: CascadeClient):
        r = client.add("a")
        assert r.success
        assert isinstance(r, Result)

    def test_add_basic(self, client: CascadeClient):
        r = client.add("a")
        assert r.success
        nodes = _nodes(client)
        assert len(nodes) == 1
        assert nodes[0].id == "a"

    def test_add_with_deps(self, client: CascadeClient):
        client.add("a")
        r = client.add("b", deps={"a": Contract("Need spec", "Deliver spec")})
        assert r.success
        nodes = _nodes(client)
        assert len(nodes) == 2

    def test_add_duplicate_fails(self, client: CascadeClient):
        client.add("a")
        r = client.add("a")
        assert not r.success


class TestAddBatch:
    def test_batch_empty(self, client: CascadeClient):
        r = client.add_batch([])
        assert r.success
        assert _nodes(client) == []

    def test_batch_simple(self, client: CascadeClient):
        r = client.add_batch(
            [
                {"node_id": "a"},
                {"node_id": "b"},
                {"node_id": "c"},
            ]
        )
        assert r.success
        assert len(_nodes(client)) == 3
        assert r.data["added"] == ["a", "b", "c"]

    def test_batch_with_internal_dependencies(self, client: CascadeClient):
        """A spec can reference a dep added earlier in the same batch."""
        r = client.add_batch(
            [
                {"node_id": "a"},
                {"node_id": "b", "deps": {"a": Contract("E", "P")}},
                {"node_id": "c", "deps": {"b": Contract("E", "P")}},
            ]
        )
        assert r.success
        nodes = {n.id: n for n in _nodes(client)}
        assert nodes["a"].state == "READY"
        assert nodes["b"].state == "PENDING"
        assert nodes["c"].state == "PENDING"

    def test_batch_atomic_on_failure(self, client: CascadeClient):
        """If any spec fails, no nodes are added."""
        r = client.add_batch(
            [
                {"node_id": "good1"},
                {"node_id": "good2"},
                {"node_id": "bad", "deps": {"nonexistent": Contract("E", "P")}},
            ]
        )
        assert not r.success
        assert "Batch failed at 'bad'" in r.message
        assert _nodes(client) == []

    def test_batch_missing_node_id(self, client: CascadeClient):
        r = client.add_batch([{"deps": {}}])
        assert not r.success
        assert "missing node_id" in r.message

    def test_batch_duplicate_in_existing_graph(self, client: CascadeClient):
        client.add("a")
        r = client.add_batch(
            [
                {"node_id": "b"},
                {"node_id": "a"},  # already exists
            ]
        )
        assert not r.success
        # neither b nor anything else added
        assert len(_nodes(client)) == 1


# ── remove() ───────────────────────────────────────────────────────────


class TestRemove:
    def test_remove_single(self, client: CascadeClient):
        client.add("a")
        r = client.remove("a")
        assert r.success
        assert _nodes(client) == []

    def test_remove_cascade(self, client: CascadeClient):
        client.add("a")
        client.add("b", deps={"a": Contract("need", "promise")})
        r = client.remove("a", cascade=True)
        assert r.success
        assert _nodes(client) == []

    def test_remove_active_node_blocked(self, client: CascadeClient):
        client.add("a")
        client.claim("w1", "a")
        r = client.remove("a")
        assert not r.success

    def test_remove_nonexistent(self, client: CascadeClient):
        r = client.remove("ghost")
        assert not r.success


# ── split() ────────────────────────────────────────────────────────────


class TestSplit:
    def test_split_basic(self, client: CascadeClient):
        client.add("big")
        r = client.split("big", into=["part1", "part2"])
        assert r.success
        ids = {n.id for n in _nodes(client)}
        assert "part1" in ids
        assert "part2" in ids
        assert "big" not in ids

    def test_split_active_blocked(self, client: CascadeClient):
        client.add("big")
        client.claim("w1", "big")
        r = client.split("big", into=["part1", "part2"])
        assert not r.success


# ── refine() ───────────────────────────────────────────────────────────


class TestRefine:
    def test_refine_add_dependency(self, client: CascadeClient):
        client.add("a")
        client.add("b")
        r = client.refine("b", "a", expectation="Need data", promise="Provide data")
        assert r.success


# ── edit() ─────────────────────────────────────────────────────────────


class TestEdit:
    def test_edit_summary(self, client: CascadeClient):
        client.add("a")
        r = client.edit("a", summary="Updated summary")
        assert r.success

    def test_edit_critical(self, client: CascadeClient):
        client.add("a")
        r = client.edit("a", critical={"lang": "python"})
        assert r.success

    def test_edit_artifacts(self, client: CascadeClient):
        client.add("a")
        r = client.edit("a", artifacts="# Design Doc\nDetails here.")
        assert r.success

    def test_edit_context_visible_on_claim(self, client: CascadeClient):
        client.add("a")
        client.edit("a", critical={"key": "val"})
        client.claim("w1", "a")


# ── claim() ────────────────────────────────────────────────────────────


class TestClaim:
    def test_claim_specific_task(self, client: CascadeClient):
        client.add("a")
        r = client.claim("w1", "a")
        assert isinstance(r, Result)
        assert r.success
        task = TaskView.from_result(r)
        assert task.id == "a"
        assert task.state == "ACTIVE"

    def test_claim_by_priority(self, client: CascadeClient):
        """Claiming without task_id picks the highest-priority READY node."""
        client.add("first")
        client.add("second")
        r = client.claim("w1")
        task = TaskView.from_result(r)
        assert task.id in ("first", "second")
        assert task.state == "ACTIVE"

    def test_claim_no_task_fails(self, client: CascadeClient):
        r = client.claim("w1")
        assert not r.success

    def test_claim_pending_task_fails(self, client: CascadeClient):
        client.add("a")
        client.add("b", deps={"a": Contract("need", "promise")})
        r = client.claim("w1", "b")
        assert not r.success

    def test_claim_returns_upstream_context(self, client: CascadeClient):
        """After completing A, claiming B should see A's output in upstream."""
        client.add("a")
        client.add("b", deps={"a": Contract("Need result", "Deliver result")})
        _t = claim_token(client, "w1", "a")
        client.complete("a", summary="Done A", critical={"out": "42"}, token=_t)
        task_b = TaskView.from_result(client.claim("w2", "b"))
        assert len(task_b.upstream) > 0
        upstream_ids = [u.get("node_id") for u in task_b.upstream]
        assert "a" in upstream_ids

    def test_claim_retries_on_lock_contention(self, client: CascadeClient, monkeypatch):
        """Lock contention should retry up to 3 times before failing."""
        from cascade.errors import LockError

        monkeypatch.setattr("cascade.client.time.sleep", lambda _: None)

        client.add("a")
        attempts = {"count": 0}
        original = client._claim_locked

        def flaky(*args, **kwargs):
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise LockError("simulated contention")
            return original(*args, **kwargs)

        monkeypatch.setattr(client, "_claim_locked", flaky)
        r = client.claim("w1", "a")
        assert r.success
        assert attempts["count"] == 3

    def test_claim_lock_failure_after_retries(self, client: CascadeClient, monkeypatch):
        """All retries failing should return clear error."""
        from cascade.errors import LockError

        monkeypatch.setattr("cascade.client.time.sleep", lambda _: None)

        client.add("a")

        def always_fails(*args, **kwargs):
            raise LockError("persistent contention")

        monkeypatch.setattr(client, "_claim_locked", always_fails)
        r = client.claim("w1", "a")
        assert not r.success
        assert "lock" in r.message.lower()


# ── complete() ─────────────────────────────────────────────────────────


class TestComplete:
    def test_complete_basic(self, client: CascadeClient):
        client.add("a")
        _t = claim_token(client, "w1", "a")
        r = client.complete("a", summary="Done", token=_t)
        assert r.success

    def test_complete_with_summary(self, client: CascadeClient):
        client.add("a")
        _t = claim_token(client, "w1", "a")
        r = client.complete("a", summary="Analysis done", token=_t)
        assert r.success

    def test_complete_with_critical(self, client: CascadeClient):
        client.add("a")
        _t = claim_token(client, "w1", "a")
        r = client.complete("a", critical={"lang": "python", "version": "3.12"}, token=_t)
        assert r.success

    def test_complete_with_artifacts(self, client: CascadeClient):
        client.add("a")
        _t = claim_token(client, "w1", "a")
        r = client.complete("a", artifacts="def hello(): pass", token=_t)
        assert r.success

    def test_complete_with_all_context(self, client: CascadeClient):
        client.add("a")
        _t = claim_token(client, "w1", "a")
        r = client.complete(
            "a",
            summary="Implemented feature",
            critical={"api": "/v1/data"},
            artifacts="class DataService: ...",
            token=_t,
        )
        assert r.success

    def test_complete_transitions_to_done(self, client: CascadeClient):
        client.add("a")
        _t = claim_token(client, "w1", "a")
        client.complete("a", summary="Done", token=_t)
        nodes = _nodes(client, state="COMPLETED")
        assert len(nodes) == 1
        assert nodes[0].id == "a"

    def test_complete_with_correct_agent_id(self, client: CascadeClient):
        client.add("a")
        _t = claim_token(client, "w1", "a")
        r = client.complete("a", agent_id="w1", summary="Done", token=_t)
        assert r.success

    def test_complete_with_wrong_agent_id_rejected(self, client: CascadeClient):
        client.add("a")
        _t = claim_token(client, "w1", "a")
        r = client.complete("a", agent_id="other-agent", summary="Done", token=_t)
        assert not r.success
        assert "claimed by 'w1'" in r.message
        nodes = _nodes(client, state="ACTIVE")
        assert len(nodes) == 1  # task still ACTIVE, not finished


# ── fail() ─────────────────────────────────────────────────────────────


class TestFail:
    def test_fail_basic(self, client: CascadeClient):
        client.add("a")
        _t = claim_token(client, "w1", "a")
        r = client.fail("a", reason="Out of memory", token=_t)
        assert r.success

    def test_fail_with_cascade(self, client: CascadeClient):
        client.add("a")
        client.add("b", deps={"a": Contract("need", "promise")})
        _t = claim_token(client, "w1", "a")
        r = client.fail("a", cascade=True, reason="Fatal error", token=_t)
        assert r.success
        # Both nodes should be in a terminal state
        remaining_ready = _nodes(client, state="READY")
        remaining_pending = _nodes(client, state="PENDING")
        assert len(remaining_ready) == 0
        assert len(remaining_pending) == 0

    def test_fail_without_reason(self, client: CascadeClient):
        client.add("a")
        _t = claim_token(client, "w1", "a")
        r = client.fail("a", token=_t)
        assert r.success


# ── release() ──────────────────────────────────────────────────────────


class TestRelease:
    def test_release_basic(self, client: CascadeClient):
        client.add("a")
        _t = claim_token(client, "w1", "a")
        r = client.release("a", reason="Need more info", token=_t)
        assert r.success
        nodes = _nodes(client, state="READY")
        assert any(n.id == "a" for n in nodes)

    def test_release_then_reclaim(self, client: CascadeClient):
        client.add("a")
        _t = claim_token(client, "w1", "a")
        client.release("a", token=_t)
        r = client.claim("w2", "a")
        assert r.success
        assert r.data["task_id"] == "a"
        assert r.data["state"] == "ACTIVE"


# ── rework() ──────────────────────────────────────────────────────────


class TestRework:
    def test_rework_flow(self, client: CascadeClient):
        """Full rework: A -> B, complete A, claim B, request rework of A."""
        client.add("a")
        client.add("b", deps={"a": Contract("Need spec", "Deliver spec")})
        # Complete A
        _t = claim_token(client, "w1", "a")
        client.complete("a", summary="Spec v1", token=_t)
        # Claim B and request rework
        client.claim("w2", "b")
        r = client.rework(
            source="a",
            corrective="a-fix",
            reason="Spec incomplete",
            agent_id="w2",
            source_expectation="Need corrected spec from a",
            source_promise="A promises corrected spec",
            corrective_expectation="B needs the fix",
            corrective_promise="Fix delivers corrected spec",
        )
        assert r.success
        ids = {n.id for n in _nodes(client)}
        assert "a-fix" in ids


# ── nodes() ────────────────────────────────────────────────────────────


class TestNodes:
    def test_returns_result(self, client: CascadeClient):
        client.add("a")
        r = client.nodes()
        assert isinstance(r, Result)
        assert r.success
        assert r.data["count"] == 1

    def test_list_all(self, client: CascadeClient):
        client.add("a")
        client.add("b")
        client.add("c")
        nodes = _nodes(client)
        assert len(nodes) == 3
        assert all(isinstance(n, NodeInfo) for n in nodes)

    def test_filter_by_state(self, client: CascadeClient):
        client.add("a")
        client.add("b", deps={"a": Contract("need", "promise")})
        ready = _nodes(client, state="READY")
        pending = _nodes(client, state="PENDING")
        assert len(ready) == 1
        assert ready[0].id == "a"
        assert len(pending) == 1
        assert pending[0].id == "b"

    def test_pending_dependencies_count(self, client: CascadeClient):
        client.add("a")
        client.add("b", deps={"a": Contract("need", "promise")})
        pending = _nodes(client, state="PENDING")
        assert pending[0].pending_dependencies >= 1

    def test_empty_graph(self, client: CascadeClient):
        nodes = _nodes(client)
        assert nodes == []

    def test_active_node_includes_agent_and_duration(self, client: CascadeClient):
        client.add("a")
        client.claim("w1", "a")
        active = _nodes(client, state="ACTIVE")
        assert len(active) == 1
        assert active[0].agent_id == "w1"
        assert active[0].active_seconds is not None
        assert active[0].active_seconds >= 0
        assert active[0].stale is False

    def test_active_node_stale_when_timed_out(self, client: CascadeClient):
        client.add("a")
        client.claim("w1", "a", timeout=0.01)
        import time as _t

        _t.sleep(0.05)
        active = _nodes(client, state="ACTIVE")
        assert active[0].stale is True

    def test_non_active_node_no_active_metadata(self, client: CascadeClient):
        client.add("a")
        ready = _nodes(client, state="READY")
        assert ready[0].agent_id is None
        assert ready[0].active_seconds is None


# ── check() ────────────────────────────────────────────────────────────


class TestCheck:
    def test_check_valid_token(self, client: CascadeClient):
        client.add("a")
        client.claim("w1", "a")
        r = client.check("a")
        assert r.success

    def test_check_invalid_token(self, client: CascadeClient):
        client.add("a")
        # Not claimed - check returns success but data.valid is False
        r = client.check("a")
        assert r.success
        assert r.data.get("valid") is False


# ── check_timeouts() ──────────────────────────────────────────────────


class TestCheckTimeouts:
    def test_timeout_releases_stalled_task(self, client: CascadeClient):
        import time

        client.add("a")
        client.claim("w1", "a", timeout=0.01)
        time.sleep(0.02)  # Wait for timeout to expire
        r = client.check_timeouts()
        assert r.success
        ready = _nodes(client, state="READY")
        assert any(n.id == "a" for n in ready)

    def test_timeout_with_default(self, client: CascadeClient):
        client.add("a")
        client.claim("w1", "a")
        # Default timeout of 0 should release everything
        r = client.check_timeouts(default_timeout=0.0)
        assert r.success


# ── Contract type ──────────────────────────────────────────────────────


class TestContract:
    def test_contract_fields(self):
        c = Contract("I need X", "I deliver X")
        assert c.expectation == "I need X"
        assert c.promise == "I deliver X"

    def test_contract_frozen(self):
        c = Contract("need", "promise")
        with pytest.raises(AttributeError):
            c.expectation = "changed"  # type: ignore[misc]

    def test_contract_used_in_deps(self, client: CascadeClient):
        client.add("a")
        contract = Contract("Expect analysis", "Deliver analysis report")
        r = client.add("b", deps={"a": contract})
        assert r.success


# ── Upstream context flow ──────────────────────────────────────────────


class TestContextFlow:
    def test_summary_flows_to_downstream(self, client: CascadeClient):
        """Complete A with summary, claim B should see it in upstream."""
        client.add("a")
        client.add("b", deps={"a": Contract("Need result", "Deliver result")})
        _t = claim_token(client, "w1", "a")
        client.complete("a", summary="Analysis complete: found 3 issues", token=_t)
        task_b = TaskView.from_result(client.claim("w2", "b"))
        found = False
        for u in task_b.upstream:
            delivered = u.get("delivered", {})
            if "Analysis complete" in delivered.get("summary", ""):
                found = True
                break
        assert found, f"Expected A's summary in upstream, got: {task_b.upstream}"

    def test_critical_flows_to_downstream(self, client: CascadeClient):
        """Complete A with critical KV, claim B should see it."""
        client.add("a")
        client.add("b", deps={"a": Contract("Need data", "Deliver data")})
        _t = claim_token(client, "w1", "a")
        client.complete("a", critical={"api_endpoint": "/v1/users"}, token=_t)
        task_b = TaskView.from_result(client.claim("w2", "b"))
        found = False
        for u in task_b.upstream:
            delivered = u.get("delivered", {})
            crit = delivered.get("critical", {})
            if crit.get("api_endpoint") == "/v1/users":
                found = True
                break
        assert found, f"Expected A's critical in upstream, got: {task_b.upstream}"
