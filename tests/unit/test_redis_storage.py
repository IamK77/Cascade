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

"""Tests for RedisStorage and all Redis sub-components."""

import time

import pytest

fakeredis = pytest.importorskip("fakeredis")

from cascade.context.context import Context  # noqa: E402
from cascade.core.cascade import Cascade  # noqa: E402
from cascade.core.node import Node  # noqa: E402
from cascade.core.state import NodeState  # noqa: E402
from cascade.events import EventType  # noqa: E402
from cascade.storage.redis_storage import (  # noqa: E402
    RedisContentStore,
    RedisEventStore,
    RedisOpLog,
    RedisStorage,
    RedisTokenStore,
)
from cascade.types import TokenStatus  # noqa: E402


@pytest.fixture
def redis_client():
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture
def prefix():
    return "cascade:test"


@pytest.fixture
def storage(redis_client):
    return RedisStorage(redis_client, namespace="test")


@pytest.fixture
def sample_cascade():
    cascade = Cascade()
    node_a = Node(
        id="a",
        state=NodeState.READY,
        context=Context(critical={"project": "test"}, summary="This is node A"),
    )
    node_b = Node(id="b", state=NodeState.PENDING)
    cascade.add_node(node_a)
    cascade.add_node(node_b)
    cascade.add_edge(
        "a",
        "b",
        expectation="Expect analysis results",
        promise="Promises to output analysis results",
    )
    return cascade


# =========================================================================
# RedisEventStore
# =========================================================================


class TestRedisEventStore:
    @pytest.fixture
    def event_store(self, redis_client, prefix):
        return RedisEventStore(redis_client, prefix)

    def test_emit_and_read_all(self, event_store):
        event_store.emit(EventType.NODE_ADDED, 1, node_id="a")
        event_store.emit(EventType.NODE_ADDED, 2, node_id="b")
        events = event_store.read_all()
        assert len(events) == 2
        assert events[0].type == EventType.NODE_ADDED
        assert events[0].data["node_id"] == "a"
        assert events[1].data["node_id"] == "b"

    def test_emit_returns_event_with_hash(self, event_store):
        event = event_store.emit(EventType.TASK_CLAIMED, 1, node_id="x")
        assert event.hash != ""
        assert event.prev_hash == ""

    def test_hash_chain(self, event_store):
        e1 = event_store.emit(EventType.NODE_ADDED, 1, node_id="a")
        e2 = event_store.emit(EventType.NODE_ADDED, 2, node_id="b")
        assert e2.prev_hash == e1.hash

    def test_verify_chain_valid(self, event_store):
        event_store.emit(EventType.NODE_ADDED, 1, node_id="a")
        event_store.emit(EventType.EDGE_ADDED, 2, from_id="a", to_id="b")
        event_store.emit(EventType.TASK_CLAIMED, 3, node_id="a")
        ok, msg = event_store.verify_chain()
        assert ok
        assert msg == ""

    def test_count(self, event_store):
        assert event_store.count == 0
        event_store.emit(EventType.NODE_ADDED, 1, node_id="a")
        assert event_store.count == 1
        event_store.emit(EventType.NODE_ADDED, 2, node_id="b")
        assert event_store.count == 2

    def test_clear(self, event_store):
        event_store.emit(EventType.NODE_ADDED, 1, node_id="a")
        event_store.clear()
        assert event_store.count == 0
        assert event_store.read_all() == []

    def test_emit_with_trace_id(self, event_store):
        event = event_store.emit(EventType.NODE_ADDED, 1, trace_id="trace-1", node_id="a")
        assert event.trace_id == "trace-1"

    def test_read_since(self, event_store):
        before = time.time()
        event_store.emit(EventType.NODE_ADDED, 1, node_id="a")
        events = event_store.read_since(before - 1)
        assert len(events) == 1

    def test_read_by_type(self, event_store):
        event_store.emit(EventType.NODE_ADDED, 1, node_id="a")
        event_store.emit(EventType.TASK_CLAIMED, 2, node_id="a")
        event_store.emit(EventType.NODE_ADDED, 3, node_id="b")
        assert len(event_store.read_by_type(EventType.NODE_ADDED)) == 2
        assert len(event_store.read_by_type(EventType.TASK_CLAIMED)) == 1

    def test_read_by_node(self, event_store):
        event_store.emit(EventType.NODE_ADDED, 1, node_id="a")
        event_store.emit(EventType.NODE_ADDED, 2, node_id="b")
        event_store.emit(EventType.TASK_CLAIMED, 3, node_id="a")
        assert len(event_store.read_by_node("a")) == 2
        assert len(event_store.read_by_node("b")) == 1

    def test_read_by_trace(self, event_store):
        event_store.emit(EventType.NODE_ADDED, 1, trace_id="t1", node_id="a")
        event_store.emit(EventType.NODE_ADDED, 2, trace_id="t2", node_id="b")
        assert len(event_store.read_by_trace("t1")) == 1

    def test_read_at(self, event_store):
        event_store.emit(EventType.NODE_ADDED, 10, node_id="a")
        event_store.emit(EventType.NODE_ADDED, 20, node_id="b")
        e = event_store.read_at(10)
        assert e is not None
        assert e.data["node_id"] == "a"
        assert event_store.read_at(99) is None

    def test_read_range(self, event_store):
        event_store.emit(EventType.NODE_ADDED, 10, node_id="a")
        event_store.emit(EventType.NODE_ADDED, 20, node_id="b")
        event_store.emit(EventType.NODE_ADDED, 30, node_id="c")
        assert len(event_store.read_range(10, 20)) == 2

    def test_read_until(self, event_store):
        event_store.emit(EventType.NODE_ADDED, 10, node_id="a")
        event_store.emit(EventType.NODE_ADDED, 20, node_id="b")
        assert len(event_store.read_until(15)) == 1

    def test_summary(self, event_store):
        event_store.emit(EventType.NODE_ADDED, 1, node_id="a")
        event_store.emit(EventType.NODE_ADDED, 2, node_id="b")
        event_store.emit(EventType.TASK_CLAIMED, 3, node_id="a")
        s = event_store.summary()
        assert s["node_added"] == 2
        assert s["task_claimed"] == 1


# =========================================================================
# RedisTokenStore
# =========================================================================


class TestRedisTokenStore:
    @pytest.fixture
    def token_store(self, redis_client, prefix):
        return RedisTokenStore(redis_client, prefix)

    def test_create_and_check(self, token_store):
        ts = token_store.create("node-1", "agent-1", time.time())
        assert ts.valid
        assert ts.node_id == "node-1"
        assert ts.agent_id == "agent-1"

        checked = token_store.check("node-1")
        assert checked is not None
        assert checked.valid

    def test_check_nonexistent(self, token_store):
        assert token_store.check("nope") is None

    def test_invalidate(self, token_store):
        token_store.create("node-1", "agent-1", time.time())
        result = token_store.invalidate("node-1", "task was split")
        assert result is not None
        assert not result.valid
        assert result.reason == "task was split"

        checked = token_store.check("node-1")
        assert not checked.valid

    def test_invalidate_nonexistent(self, token_store):
        assert token_store.invalidate("nope", "reason") is None

    def test_invalidate_already_invalid(self, token_store):
        token_store.create("node-1", "agent-1", time.time())
        token_store.invalidate("node-1", "first")
        result = token_store.invalidate("node-1", "second")
        assert result is not None
        assert not result.valid
        assert result.reason == "first"

    def test_invalidate_fires_notifier(self, token_store):
        notifications: list[TokenStatus] = []

        class Notifier:
            def notify(self, token: TokenStatus) -> None:
                notifications.append(token)

        token_store.create("node-1", "agent-1", time.time(), notifier=Notifier())
        token_store.invalidate("node-1", "cancelled")
        assert len(notifications) == 1
        assert not notifications[0].valid

    def test_cleanup(self, token_store):
        token_store.create("node-1", "agent-1", time.time())
        token_store.cleanup("node-1")
        assert token_store.check("node-1") is None

    def test_cleanup_nonexistent(self, token_store):
        token_store.cleanup("nope")


# =========================================================================
# RedisOpLog
# =========================================================================


class TestRedisOpLog:
    @pytest.fixture
    def op_log(self, redis_client, prefix):
        return RedisOpLog(redis_client, prefix)

    def test_record_and_get(self, op_log):
        op_log.record("op-1", {"status": "ok", "node_id": "a"})
        result = op_log.get("op-1")
        assert result == {"status": "ok", "node_id": "a"}

    def test_get_nonexistent(self, op_log):
        assert op_log.get("nope") is None

    def test_idempotent_record(self, op_log):
        op_log.record("op-1", {"status": "ok"})
        op_log.record("op-1", {"status": "updated"})
        assert op_log.get("op-1") == {"status": "updated"}


# =========================================================================
# RedisContentStore
# =========================================================================


class TestRedisContentStore:
    @pytest.fixture
    def content_store(self, redis_client, prefix):
        return RedisContentStore(redis_client, prefix)

    def test_put_and_get(self, content_store):
        ref = content_store.put("hello world")
        assert len(ref) == 64  # SHA-256 hex
        assert content_store.get(ref) == "hello world"

    def test_get_nonexistent(self, content_store):
        assert content_store.get("deadbeef" * 8) is None

    def test_exists(self, content_store):
        ref = content_store.put("content")
        assert content_store.exists(ref)
        assert not content_store.exists("nope")

    def test_deduplication(self, content_store):
        ref1 = content_store.put("same content")
        ref2 = content_store.put("same content")
        assert ref1 == ref2

    def test_unicode_content(self, content_store):
        text = "你好世界 🌍"
        ref = content_store.put(text)
        assert content_store.get(ref) == text


# =========================================================================
# RedisStorage (top-level)
# =========================================================================


class TestRedisStorage:
    def test_save_and_load(self, storage, sample_cascade):
        storage.save(sample_cascade)
        assert storage.exists()

        loaded = storage.load()
        assert loaded is not None
        assert len(loaded.nodes) == 2
        assert "a" in loaded.nodes
        assert "b" in loaded.nodes

    def test_load_nonexistent(self, storage):
        assert storage.load() is None

    def test_exists_false_initially(self, storage):
        assert not storage.exists()

    def test_save_preserves_node_state(self, storage, sample_cascade):
        storage.save(sample_cascade)
        loaded = storage.load()
        assert loaded.nodes["a"].state == NodeState.READY
        assert loaded.nodes["b"].state == NodeState.PENDING

    def test_save_preserves_context(self, storage, sample_cascade):
        storage.save(sample_cascade)
        loaded = storage.load()
        assert loaded.nodes["a"].context is not None
        assert loaded.nodes["a"].context.critical == {"project": "test"}
        assert loaded.nodes["a"].context.summary == "This is node A"

    def test_save_preserves_contracts(self, storage, sample_cascade):
        storage.save(sample_cascade)
        loaded = storage.load()
        contract = loaded.get_contract("a", "b")
        assert contract is not None
        assert contract.expectation == "Expect analysis results"
        assert contract.promise == "Promises to output analysis results"

    def test_save_preserves_edges(self, storage, sample_cascade):
        storage.save(sample_cascade)
        loaded = storage.load()
        dependents = loaded.get_dependents("a")
        assert len(dependents) == 1
        assert dependents[0].id == "b"

    def test_delete(self, storage, sample_cascade):
        storage.save(sample_cascade)
        storage.events.emit(EventType.NODE_ADDED, 1, node_id="a")
        storage.delete()
        assert not storage.exists()
        assert storage.events.count == 0

    def test_empty_cascade(self, storage):
        cascade = Cascade()
        storage.save(cascade)
        loaded = storage.load()
        assert loaded is not None
        assert len(loaded.nodes) == 0

    def test_node_without_context(self, storage):
        cascade = Cascade()
        cascade.add_node(Node(id="test", state=NodeState.READY))
        storage.save(cascade)
        loaded = storage.load()
        assert loaded.nodes["test"].context is None

    def test_artifacts_round_trip(self, storage):
        cascade = Cascade()
        artifacts = "# Task Artifacts\n\nFull documentation here."
        node = Node(
            id="task_a",
            state=NodeState.READY,
            context=Context(
                critical={"project": "test"},
                summary="Summary",
                artifacts=artifacts,
            ),
        )
        cascade.add_node(node)
        storage.save(cascade)

        loaded = storage.load()
        assert loaded.nodes["task_a"].context.artifacts == artifacts

    def test_save_preserves_agent_id(self, storage):
        cascade = Cascade()
        node = Node(id="task", state=NodeState.ACTIVE, agent_id="agent-001")
        cascade.add_node(node)
        storage.save(cascade)
        loaded = storage.load()
        assert loaded.nodes["task"].agent_id == "agent-001"

    def test_next_lamport_monotonic(self, storage):
        ts1 = storage.next_lamport()
        ts2 = storage.next_lamport()
        ts3 = storage.next_lamport()
        assert ts1 < ts2 < ts3

    def test_observe_advances_clock(self, storage):
        storage.next_lamport()
        far_future = int(time.time() * 1000) + 10_000_000
        storage.observe(far_future)
        ts = storage.next_lamport()
        assert ts > far_future

    def test_lock_context_manager(self, storage):
        with storage.lock():
            pass

    def test_namespace_isolation(self, redis_client):
        s1 = RedisStorage(redis_client, namespace="ns1")
        s2 = RedisStorage(redis_client, namespace="ns2")

        cascade = Cascade()
        cascade.add_node(Node(id="a", state=NodeState.READY))
        s1.save(cascade)

        assert s1.exists()
        assert not s2.exists()

    def test_multiple_save_load_cycles(self, storage):
        cascade = Cascade()
        cascade.add_node(Node(id="a", state=NodeState.READY))
        storage.save(cascade)

        loaded = storage.load()
        loaded.add_node(Node(id="b", state=NodeState.PENDING))
        loaded.add_edge("a", "b", expectation="e", promise="p")
        storage.save(loaded)

        reloaded = storage.load()
        assert len(reloaded.nodes) == 2
        assert reloaded.get_contract("a", "b") is not None

    def test_protocol_compliance(self, storage):
        from cascade.storage.protocol import StorageProtocol

        assert isinstance(storage, StorageProtocol)


# =========================================================================
# Import guard — redis not installed
# =========================================================================


class TestImportGuard:
    def test_redis_storage_in_package_all(self):
        from cascade import storage

        assert "RedisStorage" in storage.__all__
