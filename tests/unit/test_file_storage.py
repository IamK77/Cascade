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

"""Unit tests for FileStorage — covers init, lamport/HLC, locking,
save/load edge cases, atomic writes, delete, scope, and sub-components.

Complements the existing test_storage.py (round-trip / serialization focus)
with deeper coverage of the FileStorage class itself.
"""

import json
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from cascade.context.context import Context
from cascade.core.cascade import Cascade
from cascade.core.node import Node
from cascade.core.state import NodeState
from cascade.errors import LockError
from cascade.events import FileEventStore
from cascade.storage.content import LocalContentStore
from cascade.storage.file_storage import FileStorage, StorageScope
from cascade.storage.op_log import FileOpLog
from cascade.storage.protocol import StorageProtocol
from cascade.storage.token_store import FileTokenStore

# -----------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------


@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    return tmp_path / ".cascade"


@pytest.fixture
def storage(temp_dir: Path) -> FileStorage:
    return FileStorage(base_dir=temp_dir)


@pytest.fixture
def sample_cascade() -> Cascade:
    cascade = Cascade()
    cascade.add_node(
        Node(
            id="a",
            state=NodeState.READY,
            context=Context(critical={"key": "val"}, summary="summary-a"),
        )
    )
    cascade.add_node(Node(id="b", state=NodeState.PENDING))
    cascade.add_edge("a", "b", expectation="expect-ab", promise="promise-ab")
    return cascade


# -----------------------------------------------------------------------
# StorageScope enum
# -----------------------------------------------------------------------


class TestStorageScope:
    def test_values(self):
        assert StorageScope.PROJECT.value == "project"
        assert StorageScope.USER.value == "user"

    def test_members(self):
        assert set(StorageScope) == {StorageScope.PROJECT, StorageScope.USER}


# -----------------------------------------------------------------------
# __init__ / base_dir resolution
# -----------------------------------------------------------------------


class TestInit:
    def test_explicit_base_dir(self, temp_dir: Path):
        s = FileStorage(base_dir=temp_dir)
        assert s.base_dir == temp_dir

    def test_explicit_base_dir_as_string(self, temp_dir: Path):
        s = FileStorage(base_dir=str(temp_dir))
        assert s.base_dir == temp_dir

    def test_project_scope_default(self):
        with patch.object(Path, "cwd", return_value=Path("/fake/project")):
            s = FileStorage(scope=StorageScope.PROJECT)
            assert s.base_dir == Path("/fake/project/.cascade")

    def test_user_scope_default(self):
        with patch.object(Path, "home", return_value=Path("/fake/home")):
            s = FileStorage(scope=StorageScope.USER)
            assert s.base_dir == Path("/fake/home/.cascade")

    def test_explicit_base_dir_overrides_scope(self, temp_dir: Path):
        s = FileStorage(base_dir=temp_dir, scope=StorageScope.USER)
        assert s.base_dir == temp_dir

    def test_sub_components_created(self, storage: FileStorage):
        assert isinstance(storage.events, FileEventStore)
        assert isinstance(storage.tokens, FileTokenStore)
        assert isinstance(storage.ops, FileOpLog)
        assert isinstance(storage.content, LocalContentStore)

    def test_custom_content_store(self, temp_dir: Path, tmp_path: Path):
        custom = LocalContentStore(tmp_path / "custom_blobs")
        s = FileStorage(base_dir=temp_dir, content=custom)
        assert s.content is custom


# -----------------------------------------------------------------------
# Class methods: project() / user()
# -----------------------------------------------------------------------


class TestClassMethods:
    def test_project_factory(self, temp_dir: Path):
        s = FileStorage.project(base_dir=temp_dir)
        assert s.base_dir == temp_dir

    def test_project_factory_default(self):
        with patch.object(Path, "cwd", return_value=Path("/fake")):
            s = FileStorage.project()
            assert s.base_dir == Path("/fake/.cascade")

    def test_user_factory(self):
        with patch.object(Path, "home", return_value=Path("/fake/home")):
            s = FileStorage.user()
            assert s.base_dir == Path("/fake/home/.cascade")


# -----------------------------------------------------------------------
# Protocol conformance
# -----------------------------------------------------------------------


class TestProtocol:
    def test_satisfies_storage_protocol(self, storage: FileStorage):
        assert isinstance(storage, StorageProtocol)


# -----------------------------------------------------------------------
# _recover_lamport
# -----------------------------------------------------------------------


class TestRecoverLamport:
    def test_no_graph_file(self, storage: FileStorage):
        # No graph.json => lamport starts at 0
        assert storage._lamport == 0

    def test_reads_existing_lamport(self, temp_dir: Path):
        temp_dir.mkdir(parents=True, exist_ok=True)
        (temp_dir / "graph.json").write_text(
            json.dumps({"lamport": 42, "nodes": {}, "edges": []}), encoding="utf-8"
        )
        s = FileStorage(base_dir=temp_dir)
        assert s._lamport == 42

    def test_corrupt_json(self, temp_dir: Path):
        temp_dir.mkdir(parents=True, exist_ok=True)
        (temp_dir / "graph.json").write_text("{bad json", encoding="utf-8")
        s = FileStorage(base_dir=temp_dir)
        assert s._lamport == 0

    def test_missing_lamport_key(self, temp_dir: Path):
        temp_dir.mkdir(parents=True, exist_ok=True)
        (temp_dir / "graph.json").write_text(
            json.dumps({"nodes": {}, "edges": []}), encoding="utf-8"
        )
        s = FileStorage(base_dir=temp_dir)
        assert s._lamport == 0

    def test_lamport_non_integer(self, temp_dir: Path):
        temp_dir.mkdir(parents=True, exist_ok=True)
        (temp_dir / "graph.json").write_text(
            json.dumps({"lamport": "not_a_number", "nodes": {}, "edges": []}), encoding="utf-8"
        )
        s = FileStorage(base_dir=temp_dir)
        # ValueError caught => falls back to 0
        assert s._lamport == 0


# -----------------------------------------------------------------------
# next_lamport (HLC)
# -----------------------------------------------------------------------


class TestNextLamport:
    def test_monotonically_increasing(self, storage: FileStorage):
        values = [storage.next_lamport() for _ in range(10)]
        assert values == sorted(values)
        assert len(set(values)) == 10  # all unique

    def test_embeds_physical_time(self, storage: FileStorage):
        before_ms = int(time.time() * 1000)
        ts = storage.next_lamport()
        # HLC = max(physical_ms, last) + 1, so ts >= before_ms + 1
        assert ts >= before_ms

    def test_never_goes_backward(self, storage: FileStorage):
        # Force lamport far into the future
        storage._lamport = int(time.time() * 1000) + 1_000_000
        ts = storage.next_lamport()
        assert ts > storage._lamport - 1  # must exceed the forced value


# -----------------------------------------------------------------------
# observe (HLC merge)
# -----------------------------------------------------------------------


class TestObserve:
    def test_advance_past_remote(self, storage: FileStorage):
        storage._lamport = 10
        storage.observe(100)
        assert storage._lamport == 100

    def test_no_regression(self, storage: FileStorage):
        storage._lamport = 200
        storage.observe(50)
        assert storage._lamport == 200

    def test_observe_then_next(self, storage: FileStorage):
        storage.observe(999_999_999_999)
        ts = storage.next_lamport()
        assert ts > 999_999_999_999


# -----------------------------------------------------------------------
# exists()
# -----------------------------------------------------------------------


class TestExists:
    def test_false_before_save(self, storage: FileStorage):
        assert not storage.exists()

    def test_true_after_save(self, storage: FileStorage, sample_cascade: Cascade):
        storage.save(sample_cascade)
        assert storage.exists()

    def test_false_after_delete(self, storage: FileStorage, sample_cascade: Cascade):
        storage.save(sample_cascade)
        storage.delete()
        assert not storage.exists()


# -----------------------------------------------------------------------
# lock()
# -----------------------------------------------------------------------


class TestLock:
    def test_lock_creates_base_dir(self, storage: FileStorage):
        assert not storage.base_dir.exists()
        with storage.lock():
            assert storage.base_dir.exists()

    def test_lock_reentrance_blocked(self, storage: FileStorage):
        """A second lock attempt from another thread should block then succeed."""
        results = []

        def worker():
            with storage.lock(timeout=5):
                results.append("acquired")
                time.sleep(0.05)

        with storage.lock():
            t = threading.Thread(target=worker)
            t.start()
            time.sleep(0.05)  # Give the thread time to block
            # Thread should still be waiting
            assert len(results) == 0

        t.join(timeout=5)
        assert results == ["acquired"]

    def test_lock_nonblocking_thread_contention(self, storage: FileStorage):
        """Non-blocking lock should raise LockError if thread lock held."""
        barrier = threading.Barrier(2, timeout=5)
        errors = []

        def worker():
            barrier.wait()
            try:
                with storage.lock(blocking=False):
                    pass
            except LockError as e:
                errors.append(str(e))

        with storage.lock():
            t = threading.Thread(target=worker)
            t.start()
            barrier.wait()
            time.sleep(0.05)

        t.join(timeout=5)
        assert len(errors) == 1
        assert "another thread" in errors[0]

    def test_lock_timeout_raises_lock_error(self, storage: FileStorage):
        """File lock held by another thread should cause LockError."""
        storage.base_dir.mkdir(parents=True, exist_ok=True)
        holder_ready = threading.Event()
        holder_release = threading.Event()

        def hold_file_lock():
            from filelock import FileLock

            fl = FileLock(storage.base_dir / ".lock")
            with fl.acquire():
                holder_ready.set()
                holder_release.wait(timeout=10)

        t = threading.Thread(target=hold_file_lock)
        t.start()
        holder_ready.wait(timeout=5)

        try:
            # Create a second FileStorage that shares the lock file path
            s2 = FileStorage(base_dir=storage.base_dir)
            with pytest.raises(LockError, match="Could not acquire lock"):
                with s2.lock(timeout=0.1):
                    pass
        finally:
            holder_release.set()
            t.join(timeout=5)

    def test_lock_releases_thread_lock_on_file_timeout(self, storage: FileStorage):
        """Thread lock must be released even if file lock times out."""
        storage.base_dir.mkdir(parents=True, exist_ok=True)
        holder_ready = threading.Event()
        holder_release = threading.Event()

        def hold_file_lock():
            from filelock import FileLock

            fl = FileLock(storage.base_dir / ".lock")
            with fl.acquire():
                holder_ready.set()
                holder_release.wait(timeout=10)

        t = threading.Thread(target=hold_file_lock)
        t.start()
        holder_ready.wait(timeout=5)

        try:
            s2 = FileStorage(base_dir=storage.base_dir)
            with pytest.raises(LockError):
                with s2.lock(timeout=0.1):
                    pass

            # Thread lock should be released — we can acquire it again
            assert s2._thread_lock.acquire(timeout=1)
            s2._thread_lock.release()
        finally:
            holder_release.set()
            t.join(timeout=5)


# -----------------------------------------------------------------------
# save()
# -----------------------------------------------------------------------


class TestSave:
    def test_creates_base_dir(self, storage: FileStorage, sample_cascade: Cascade):
        assert not storage.base_dir.exists()
        storage.save(sample_cascade)
        assert storage.base_dir.exists()

    def test_graph_json_is_valid_json(self, storage: FileStorage, sample_cascade: Cascade):
        storage.save(sample_cascade)
        data = json.loads((storage.base_dir / "graph.json").read_text(encoding="utf-8"))
        assert "nodes" in data
        assert "edges" in data

    def test_overwrites_previous(self, storage: FileStorage):
        c1 = Cascade()
        c1.add_node(Node(id="old", state=NodeState.READY))
        storage.save(c1)

        c2 = Cascade()
        c2.add_node(Node(id="new", state=NodeState.READY))
        storage.save(c2)

        loaded = storage.load()
        assert "new" in loaded.nodes
        assert "old" not in loaded.nodes

    def test_lamport_persisted(self, storage: FileStorage, sample_cascade: Cascade):
        ts = storage.next_lamport()
        storage.save(sample_cascade)
        data = json.loads((storage.base_dir / "graph.json").read_text(encoding="utf-8"))
        assert data["lamport"] == ts

    def test_epoch_persisted(self, storage: FileStorage):
        cascade = Cascade()
        cascade.epoch = 7
        storage.save(cascade)
        data = json.loads((storage.base_dir / "graph.json").read_text(encoding="utf-8"))
        assert data["epoch"] == 7


# -----------------------------------------------------------------------
# _atomic_write
# -----------------------------------------------------------------------


class TestAtomicWrite:
    def test_no_tmp_leftover(self, storage: FileStorage, sample_cascade: Cascade):
        storage.save(sample_cascade)
        assert not (storage.base_dir / "graph.json.tmp").exists()

    def test_content_written_correctly(self, tmp_path: Path):
        path = tmp_path / "test.json"
        content = '{"hello": "world"}'
        FileStorage._atomic_write(path, content)
        assert path.read_text(encoding="utf-8") == content

    def test_replaces_existing_file(self, tmp_path: Path):
        path = tmp_path / "test.json"
        path.write_text("old", encoding="utf-8")
        FileStorage._atomic_write(path, "new")
        assert path.read_text(encoding="utf-8") == "new"


# -----------------------------------------------------------------------
# load()
# -----------------------------------------------------------------------


class TestLoad:
    def test_returns_none_no_file(self, storage: FileStorage):
        assert storage.load() is None

    def test_returns_none_corrupt_json(self, storage: FileStorage):
        storage.base_dir.mkdir(parents=True, exist_ok=True)
        (storage.base_dir / "graph.json").write_text("not-json!!!", encoding="utf-8")
        assert storage.load() is None

    def test_load_restores_lamport(self, storage: FileStorage, sample_cascade: Cascade):
        storage.next_lamport()
        storage.next_lamport()
        expected = storage._lamport
        storage.save(sample_cascade)

        s2 = FileStorage(base_dir=storage.base_dir)
        assert s2._lamport == expected

    def test_load_updates_internal_lamport(self, storage: FileStorage, sample_cascade: Cascade):
        storage._lamport = 12345
        storage.save(sample_cascade)
        storage._lamport = 0  # reset

        loaded = storage.load()
        assert loaded is not None
        assert storage._lamport == 12345

    def test_round_trip_full_graph(self, storage: FileStorage):
        cascade = Cascade()
        cascade.epoch = 3
        cascade.add_node(
            Node(
                id="x",
                state=NodeState.ACTIVE,
                agent_id="agent-x",
                context=Context(
                    critical={"a": 1, "b": "two"},
                    summary="summary-x",
                    artifacts="# Artifacts\nContent here.",
                ),
                claimed_at=1234567890.0,
                timeout=3600.0,
            )
        )
        cascade.add_node(Node(id="y", state=NodeState.PENDING))
        cascade.add_edge("x", "y", expectation="expect-xy", promise="promise-xy")

        storage.save(cascade)
        loaded = storage.load()

        assert loaded.epoch == 3
        assert loaded.nodes["x"].state == NodeState.ACTIVE
        assert loaded.nodes["x"].agent_id == "agent-x"
        assert loaded.nodes["x"].claimed_at == 1234567890.0
        assert loaded.nodes["x"].timeout == 3600.0
        assert loaded.nodes["x"].context.critical == {"a": 1, "b": "two"}
        assert loaded.nodes["x"].context.summary == "summary-x"
        assert loaded.nodes["x"].context.artifacts == "# Artifacts\nContent here."
        assert loaded.nodes["y"].state == NodeState.PENDING
        contract = loaded.get_contract("x", "y")
        assert contract.expectation == "expect-xy"
        assert contract.promise == "promise-xy"


# -----------------------------------------------------------------------
# delete()
# -----------------------------------------------------------------------


class TestDelete:
    def test_delete_removes_directory(self, storage: FileStorage, sample_cascade: Cascade):
        storage.save(sample_cascade)
        storage.delete()
        assert not storage.base_dir.exists()

    def test_delete_nonexistent_dir(self, storage: FileStorage):
        # Should not raise even if base_dir never existed
        storage.delete()

    def test_delete_removes_all_contents(self, storage: FileStorage, sample_cascade: Cascade):
        storage.save(sample_cascade)
        # Create some extra files
        (storage.base_dir / "extra.txt").write_text("extra", encoding="utf-8")
        sub = storage.base_dir / "subdir"
        sub.mkdir()
        (sub / "nested.txt").write_text("nested", encoding="utf-8")

        storage.delete()
        assert not storage.base_dir.exists()


# -----------------------------------------------------------------------
# Thread safety
# -----------------------------------------------------------------------


class TestThreadSafety:
    def test_concurrent_saves(self, storage: FileStorage):
        """Multiple threads saving concurrently should not corrupt the file."""
        errors = []

        def worker(node_id: str):
            try:
                cascade = Cascade()
                cascade.add_node(Node(id=node_id, state=NodeState.READY))
                with storage.lock():
                    storage.save(cascade)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(f"n{i}",)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors
        # File should be valid JSON at the end
        loaded = storage.load()
        assert loaded is not None

    def test_concurrent_load_save(self, storage: FileStorage):
        """Concurrent reads and writes should not crash."""
        cascade = Cascade()
        cascade.add_node(Node(id="root", state=NodeState.READY))
        storage.save(cascade)

        errors = []

        def reader():
            try:
                for _ in range(10):
                    storage.load()
            except Exception as e:
                errors.append(e)

        def writer():
            try:
                for i in range(10):
                    c = Cascade()
                    c.add_node(Node(id=f"w{i}", state=NodeState.READY))
                    with storage.lock():
                        storage.save(c)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=reader),
            threading.Thread(target=reader),
            threading.Thread(target=writer),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        assert not errors


# -----------------------------------------------------------------------
# Edge cases
# -----------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_cascade_round_trip(self, storage: FileStorage):
        cascade = Cascade()
        storage.save(cascade)
        loaded = storage.load()
        assert loaded is not None
        assert len(loaded.nodes) == 0

    def test_unicode_in_context(self, storage: FileStorage):
        cascade = Cascade()
        cascade.add_node(
            Node(
                id="uni",
                state=NodeState.READY,
                context=Context(
                    critical={"lang": "多语言"},
                    summary="日本語テスト",
                    artifacts="한국어 内容",
                ),
            )
        )
        storage.save(cascade)
        loaded = storage.load()
        assert loaded.nodes["uni"].context.critical == {"lang": "多语言"}
        assert loaded.nodes["uni"].context.summary == "日本語テスト"
        assert loaded.nodes["uni"].context.artifacts == "한국어 内容"

    def test_large_graph(self, storage: FileStorage):
        cascade = Cascade()
        # 100 nodes in a chain
        for i in range(100):
            cascade.add_node(Node(id=f"n{i}", state=NodeState.READY))
        for i in range(99):
            cascade.add_edge(f"n{i}", f"n{i + 1}", expectation=f"e{i}", promise=f"p{i}")
        storage.save(cascade)
        loaded = storage.load()
        assert len(loaded.nodes) == 100

    def test_all_node_states(self, storage: FileStorage):
        """Verify every NodeState survives a save/load round-trip."""
        cascade = Cascade()
        # Add a READY node that PENDING depends on, so PENDING stays PENDING
        cascade.add_node(Node(id="node_READY", state=NodeState.READY))
        cascade.add_node(Node(id="node_PENDING", state=NodeState.PENDING))
        cascade.add_edge("node_READY", "node_PENDING", expectation="e", promise="p")
        cascade.add_node(Node(id="node_ACTIVE", state=NodeState.ACTIVE, agent_id="a"))
        cascade.add_node(Node(id="node_COMPLETED", state=NodeState.COMPLETED))
        cascade.add_node(Node(id="node_CANCELLED", state=NodeState.CANCELLED))
        cascade.add_node(Node(id="node_FAILED", state=NodeState.FAILED))

        storage.save(cascade)
        loaded = storage.load()
        for state in NodeState:
            assert loaded.nodes[f"node_{state.name}"].state == state

    def test_node_with_timeout_and_claimed_at(self, storage: FileStorage):
        cascade = Cascade()
        cascade.add_node(
            Node(
                id="timed",
                state=NodeState.ACTIVE,
                agent_id="a1",
                claimed_at=1000.5,
                timeout=60.0,
            )
        )
        storage.save(cascade)
        loaded = storage.load()
        assert loaded.nodes["timed"].claimed_at == 1000.5
        assert loaded.nodes["timed"].timeout == 60.0

    def test_multiple_edges_between_groups(self, storage: FileStorage):
        cascade = Cascade()
        cascade.add_node(Node(id="a1", state=NodeState.READY))
        cascade.add_node(Node(id="a2", state=NodeState.READY))
        cascade.add_node(Node(id="b1", state=NodeState.PENDING))
        cascade.add_edge("a1", "b1", expectation="e1", promise="p1")
        cascade.add_edge("a2", "b1", expectation="e2", promise="p2")
        storage.save(cascade)
        loaded = storage.load()
        c1 = loaded.get_contract("a1", "b1")
        c2 = loaded.get_contract("a2", "b1")
        assert c1.expectation == "e1"
        assert c2.expectation == "e2"
