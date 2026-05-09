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

"""Chaos tests — deliberately break things and verify recovery.

Tests system resilience under:
- Corrupted storage (graph.json, events.jsonl)
- Mid-operation crashes (simulated via monkeypatch)
- Concurrent access (multi-threaded contention)
- Event log tampering (hash chain verification)
- Replay-based disaster recovery
"""

from __future__ import annotations

import json
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

from cascade.client import CascadeClient
from cascade.core.state import NodeState
from cascade.replay import verify
from cascade.storage.file_storage import FileStorage
from cascade.types import Contract


def _make_client() -> tuple[CascadeClient, FileStorage, Path]:
    tmpdir = tempfile.mkdtemp()
    path = Path(tmpdir)
    storage = FileStorage(path)
    client = CascadeClient(storage)
    return client, storage, path


# ---------------------------------------------------------------------------
# 1. Corrupted graph.json
# ---------------------------------------------------------------------------


class TestCorruptedGraph:
    def test_load_empty_file(self):
        """graph.json exists but is empty — load should return None gracefully."""
        client, storage, path = _make_client()
        client.add("a")
        (path / "graph.json").write_text("", encoding="utf-8")
        with storage.lock():
            graph = storage.load()
        assert graph is None

    def test_load_invalid_json(self):
        """graph.json contains garbage — load should return None, not crash."""
        client, storage, path = _make_client()
        client.add("a")
        (path / "graph.json").write_text("{invalid json!!", encoding="utf-8")
        with storage.lock():
            graph = storage.load()
        assert graph is None

    def test_load_valid_json_wrong_structure(self):
        """graph.json is valid JSON but not a graph — should not crash."""
        client, storage, path = _make_client()
        client.add("a")
        (path / "graph.json").write_text('{"hello": "world"}', encoding="utf-8")
        with storage.lock():
            graph = storage.load()
        assert graph is not None
        assert len(graph.nodes) == 0

    def test_load_partial_node_data(self):
        """Node missing required fields — deserialize should handle gracefully."""
        client, storage, path = _make_client()
        client.add("a")
        graph_data = {
            "epoch": 0,
            "lamport": 0,
            "nodes": {"a": {"id": "a"}},
            "edges": [],
        }
        (path / "graph.json").write_text(json.dumps(graph_data), encoding="utf-8")
        with storage.lock():
            graph = storage.load()
        assert graph is not None
        assert "a" in graph.nodes
        assert graph.nodes["a"].state == NodeState.READY

    def test_recovery_from_events_after_corruption(self):
        """After graph.json corruption, events can rebuild the graph."""
        client, storage, path = _make_client()
        client.add("a")
        client.add("b", deps={"a": Contract("E", "P")})
        r = client.claim("w1", "a")
        token = r.data["token"]
        client.complete("a", token=token, summary="done", deliverables={"b": "out"})

        (path / "graph.json").write_text("CORRUPTED", encoding="utf-8")

        events = storage.events.read_all()
        from cascade.replay import replay

        recovered = replay(events, content=storage.content)
        assert "a" in recovered.nodes
        assert "b" in recovered.nodes
        assert recovered.nodes["a"].state == NodeState.COMPLETED
        assert recovered.nodes["b"].state == NodeState.READY


# ---------------------------------------------------------------------------
# 2. Corrupted event log
# ---------------------------------------------------------------------------


class TestCorruptedEvents:
    def test_tampered_event_detected_by_chain(self):
        """Modifying an event mid-log should break the hash chain."""
        client, storage, path = _make_client()
        client.add("a")
        client.add("b")

        events_path = path / "events.jsonl"
        lines = events_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) >= 2

        tampered = json.loads(lines[0])
        tampered["data"]["node_id"] = "TAMPERED"
        lines[0] = json.dumps(tampered, ensure_ascii=False)
        events_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        valid, msg = storage.events.verify_chain()
        assert not valid
        assert "tampered" in msg.lower() or "mismatch" in msg.lower()

    def test_truncated_event_log(self):
        """Partial event log (crash during write) — should still parse what exists."""
        client, storage, path = _make_client()
        client.add("a")
        client.add("b")
        client.add("c")

        events_path = path / "events.jsonl"
        lines = events_path.read_text(encoding="utf-8").strip().split("\n")
        events_path.write_text("\n".join(lines[:2]) + "\n", encoding="utf-8")

        events = storage.events.read_all()
        assert len(events) == 2

    def test_event_log_with_trailing_garbage(self):
        """Incomplete line at end (crash mid-write) — should skip it."""
        client, storage, path = _make_client()
        client.add("a")

        events_path = path / "events.jsonl"
        with open(events_path, "a", encoding="utf-8") as f:
            f.write('{"incomplete": tru')

        events = storage.events.read_all()
        assert len(events) == 1

    def test_empty_event_log(self):
        """Event log exists but is empty — should return empty list."""
        client, storage, path = _make_client()
        events_path = path / "events.jsonl"
        events_path.parent.mkdir(parents=True, exist_ok=True)
        events_path.write_text("", encoding="utf-8")

        events = storage.events.read_all()
        assert events == []


# ---------------------------------------------------------------------------
# 3. Atomic write resilience
# ---------------------------------------------------------------------------


class TestAtomicWrite:
    def test_tmp_file_cleanup_on_success(self):
        """After successful save, no .tmp file should remain."""
        client, storage, path = _make_client()
        client.add("a")
        tmp_files = list(path.glob("*.tmp"))
        assert len(tmp_files) == 0

    def test_graph_survives_concurrent_read_during_write(self):
        """Reading graph.json while another thread writes should not crash."""
        client, storage, path = _make_client()
        client.add("a")

        errors = []

        def writer():
            for _ in range(20):
                try:
                    client.add(f"w{time.time()}")
                except Exception as e:
                    errors.append(("writer", e))

        def reader():
            for _ in range(20):
                try:
                    graph_path = path / "graph.json"
                    if graph_path.exists():
                        text = graph_path.read_text(encoding="utf-8")
                        if text.strip():
                            json.loads(text)
                except json.JSONDecodeError:
                    pass
                except Exception as e:
                    errors.append(("reader", e))

        t1 = threading.Thread(target=writer)
        t2 = threading.Thread(target=reader)
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        non_json_errors = [e for e in errors if not isinstance(e[1], json.JSONDecodeError)]
        assert non_json_errors == [], f"Unexpected errors: {non_json_errors}"


# ---------------------------------------------------------------------------
# 4. Mid-operation crash simulation
# ---------------------------------------------------------------------------


class TestMidOperationCrash:
    def test_crash_after_event_before_save(self):
        """If process crashes after emitting event but before saving graph,
        the graph and events will be inconsistent. verify() should detect this."""
        client, storage, path = _make_client()
        client.add("a")

        def crash_on_save(graph):
            raise RuntimeError("Simulated crash")

        with patch.object(storage, "save", side_effect=crash_on_save):
            try:
                client.add("b")
            except Exception:
                pass

        with storage.lock():
            snapshot = storage.load()
        events = storage.events.read_all()

        if snapshot is not None and len(events) > 0:
            diffs = verify(events, snapshot)
            if any("node_added" in str(e).lower() for e in events if e.data.get("node_id") == "b"):
                assert len(diffs) > 0, "Crash should cause replay/snapshot divergence"

    def test_graph_intact_after_failed_operation(self):
        """A failed operation should not corrupt the existing graph state."""
        client, storage, path = _make_client()
        client.add("a")
        r = client.claim("w1", "a")
        token = r.data["token"]

        r = client.complete("nonexistent", token=token)
        assert not r.success

        with storage.lock():
            graph = storage.load()
        assert graph is not None
        assert "a" in graph.nodes
        assert graph.nodes["a"].state == NodeState.ACTIVE


# ---------------------------------------------------------------------------
# 5. Concurrent multi-agent contention
# ---------------------------------------------------------------------------


class TestConcurrentAccess:
    def test_two_agents_claim_same_task(self):
        """Two threads claiming the same task — exactly one should succeed."""
        client, storage, path = _make_client()
        client.add("a")

        results = []

        def claim(agent_id):
            r = client.claim(agent_id, "a")
            results.append((agent_id, r.success))

        t1 = threading.Thread(target=claim, args=("w1",))
        t2 = threading.Thread(target=claim, args=("w2",))
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        successes = [r for r in results if r[1]]
        assert len(successes) == 1, f"Expected exactly 1 success, got {successes}"

    def test_concurrent_add_nodes(self):
        """Multiple threads adding different nodes — all should succeed."""
        client, storage, path = _make_client()

        errors = []

        def add_node(nid):
            try:
                r = client.add(nid)
                if not r.success:
                    errors.append((nid, r.message))
            except Exception as e:
                errors.append((nid, str(e)))

        threads = [threading.Thread(target=add_node, args=(f"n{i}",)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert errors == [], f"Errors during concurrent add: {errors}"

        with storage.lock():
            graph = storage.load()
        assert graph is not None
        assert len(graph.nodes) == 10

    def test_concurrent_claim_different_tasks(self):
        """Multiple agents claiming different tasks — all should succeed."""
        client, storage, path = _make_client()
        for i in range(5):
            client.add(f"task{i}")

        results = []

        def claim(agent_id, task_id):
            r = client.claim(agent_id, task_id)
            results.append((agent_id, task_id, r.success))

        threads = [threading.Thread(target=claim, args=(f"w{i}", f"task{i}")) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        successes = [r for r in results if r[2]]
        assert len(successes) == 5, f"Expected 5 successes, got {len(successes)}: {results}"


# ---------------------------------------------------------------------------
# 6. Fencing token under contention
# ---------------------------------------------------------------------------


class TestFencingTokenResilience:
    def test_stale_token_after_release_reclaim(self):
        """Token from first claim must be rejected after release + reclaim."""
        client, _, _ = _make_client()
        client.add("a")

        r1 = client.claim("w1", "a")
        old_token = r1.data["token"]

        client.release("a", token=old_token)
        r2 = client.claim("w2", "a")
        new_token = r2.data["token"]

        r = client.complete("a", token=old_token)
        assert not r.success, "Stale token should be rejected"

        r = client.complete("a", token=new_token)
        assert r.success, "Current token should work"

    def test_token_epoch_advances_monotonically(self):
        """Each claim/release cycle should advance the epoch."""
        client, storage, _ = _make_client()
        client.add("a")

        tokens = []
        for i in range(5):
            r = client.claim(f"w{i}", "a")
            assert r.success
            tokens.append(r.data["token"])
            client.release("a", token=r.data["token"])

        for i in range(1, len(tokens)):
            assert tokens[i] > tokens[i - 1], (
                f"Token {i} ({tokens[i]}) should be > token {i - 1} ({tokens[i - 1]})"
            )


# ---------------------------------------------------------------------------
# 7. Recovery: replay rebuilds exact state
# ---------------------------------------------------------------------------


class TestDisasterRecovery:
    def test_full_workflow_recovery(self):
        """Complex workflow: add, claim, complete, fail, rework — then
        destroy graph.json and verify replay rebuilds identical state."""
        client, storage, path = _make_client()

        client.add("a")
        client.add("b", deps={"a": Contract("E1", "P1")})
        client.add("c", deps={"a": Contract("E2", "P2")})

        r = client.claim("w1", "a")
        token = r.data["token"]
        client.complete(
            "a",
            token=token,
            summary="done",
            deliverables={"b": "output-b", "c": "output-c"},
        )

        r = client.claim("w2", "b")
        token_b = r.data["token"]
        client.fail("b", token=token_b, reason="oom")

        with storage.lock():
            snapshot = storage.load()

        (path / "graph.json").unlink()
        assert not (path / "graph.json").exists()

        events = storage.events.read_all()
        diffs = verify(events, snapshot, content=storage.content)
        assert diffs == [], f"Recovery diverged: {diffs}"

    def test_hash_chain_intact_after_full_workflow(self):
        """Hash chain should be valid after a complex workflow."""
        client, storage, _ = _make_client()

        client.add("x")
        client.add("y", deps={"x": Contract("E", "P")})
        r = client.claim("w1", "x")
        client.complete("x", token=r.data["token"], summary="ok", deliverables={"y": "out"})
        r2 = client.claim("w2", "y")
        client.complete("y", token=r2.data["token"], summary="ok")

        valid, msg = storage.events.verify_chain()
        assert valid, f"Hash chain broken: {msg}"
