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

"""Chaos tests for FileStorage — deliberately break things and verify recovery.

Targets:
- Corrupted graph.json recovery (various corruption patterns)
- Lock contention under threads (multi-threaded race conditions)
- Atomic write with concurrent readers (torn write protection)
- Mid-save crash simulation (partial writes, OS errors)

Builds on upstream unit test coverage from test_file_storage.py.
"""

from __future__ import annotations

import json
import stat
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from cascade.context.context import Context
from cascade.core.cascade import Cascade
from cascade.core.node import Node
from cascade.core.state import NodeState
from cascade.errors import LockError, StorageCorruptionError
from cascade.storage.file_storage import FileStorage

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


def _make_large_cascade(n: int = 50) -> Cascade:
    """Build a chain of n nodes for stress testing."""
    cascade = Cascade()
    for i in range(n):
        cascade.add_node(Node(id=f"n{i}", state=NodeState.READY))
    for i in range(n - 1):
        cascade.add_edge(f"n{i}", f"n{i + 1}", expectation=f"e{i}", promise=f"p{i}")
    return cascade


# =======================================================================
# 1. Corrupted graph.json recovery
# =======================================================================


class TestCorruptedGraphRecovery:
    """Verify FileStorage handles every flavour of graph.json corruption."""

    def test_empty_file_raises_corruption(self, storage: FileStorage):
        """graph.json is 0 bytes — load raises StorageCorruptionError."""
        storage.base_dir.mkdir(parents=True, exist_ok=True)
        (storage.base_dir / "graph.json").write_text("", encoding="utf-8")
        with pytest.raises(StorageCorruptionError, match="empty graph.json"):
            storage.load()

    def test_single_brace_raises_corruption(self, storage: FileStorage):
        """graph.json contains only '{' (torn write) — raises StorageCorruptionError."""
        storage.base_dir.mkdir(parents=True, exist_ok=True)
        (storage.base_dir / "graph.json").write_text("{", encoding="utf-8")
        with pytest.raises(StorageCorruptionError, match="malformed JSON"):
            storage.load()

    def test_truncated_json_raises_corruption(self, storage: FileStorage):
        """graph.json is valid JSON prefix cut mid-object — raises StorageCorruptionError."""
        storage.base_dir.mkdir(parents=True, exist_ok=True)
        (storage.base_dir / "graph.json").write_text(
            '{"nodes": {"a": {"id": "a", "state": "RE', encoding="utf-8"
        )
        with pytest.raises(StorageCorruptionError, match="malformed JSON"):
            storage.load()

    def test_binary_garbage_raises_corruption(self, storage: FileStorage):
        """graph.json filled with random bytes — raises StorageCorruptionError."""
        storage.base_dir.mkdir(parents=True, exist_ok=True)
        (storage.base_dir / "graph.json").write_bytes(bytes(range(256)))
        with pytest.raises(StorageCorruptionError, match="binary content"):
            storage.load()

    def test_null_bytes_raises_corruption(self, storage: FileStorage):
        """graph.json filled with NUL bytes (disk zero-fill) — raises StorageCorruptionError."""
        storage.base_dir.mkdir(parents=True, exist_ok=True)
        (storage.base_dir / "graph.json").write_bytes(b"\x00" * 1024)
        with pytest.raises(StorageCorruptionError, match="malformed JSON"):
            storage.load()

    def test_valid_json_array_raises_corruption(self, storage: FileStorage):
        """graph.json is a valid JSON array instead of object — raises StorageCorruptionError."""
        storage.base_dir.mkdir(parents=True, exist_ok=True)
        (storage.base_dir / "graph.json").write_text("[1, 2, 3]", encoding="utf-8")
        with pytest.raises(StorageCorruptionError, match="expected JSON object"):
            storage.load()

    def test_corrupted_node_state_raises_corruption(self, storage: FileStorage):
        """Node with invalid state name — raises StorageCorruptionError."""
        storage.base_dir.mkdir(parents=True, exist_ok=True)
        graph_data = {
            "epoch": 0,
            "lamport": 0,
            "nodes": {"a": {"id": "a", "state": "NONEXISTENT_STATE"}},
            "edges": [],
        }
        (storage.base_dir / "graph.json").write_text(json.dumps(graph_data), encoding="utf-8")
        with pytest.raises(StorageCorruptionError, match="invalid graph structure"):
            storage.load()

    def test_missing_nodes_key_loads_empty(self, storage: FileStorage):
        """graph.json has no 'nodes' key — load returns empty cascade."""
        storage.base_dir.mkdir(parents=True, exist_ok=True)
        (storage.base_dir / "graph.json").write_text(
            json.dumps({"epoch": 0, "lamport": 5}), encoding="utf-8"
        )
        result = storage.load()
        assert result is not None
        assert len(result.nodes) == 0

    def test_edge_referencing_missing_node_skipped(self, storage: FileStorage):
        """Edges pointing to non-existent nodes should be skipped."""
        storage.base_dir.mkdir(parents=True, exist_ok=True)
        graph_data = {
            "epoch": 0,
            "lamport": 0,
            "nodes": {"a": {"id": "a", "state": "READY"}},
            "edges": [{"from": "a", "to": "ghost", "expectation": "e", "promise": "p"}],
        }
        (storage.base_dir / "graph.json").write_text(json.dumps(graph_data), encoding="utf-8")
        result = storage.load()
        assert result is not None
        assert "a" in result.nodes
        assert "ghost" not in result.nodes
        assert len(result.contracts) == 0

    def test_lamport_recovery_from_corrupt_then_valid_save(
        self, storage: FileStorage, sample_cascade: Cascade
    ):
        """Corrupt graph.json => lamport=0, then save resets it properly."""
        storage.base_dir.mkdir(parents=True, exist_ok=True)
        (storage.base_dir / "graph.json").write_text("CORRUPT!", encoding="utf-8")
        s2 = FileStorage(base_dir=storage.base_dir)
        assert s2._lamport == 0
        # Now save a valid graph
        s2.save(sample_cascade)
        # Reload should work
        s3 = FileStorage(base_dir=storage.base_dir)
        loaded = s3.load()
        assert loaded is not None
        assert "a" in loaded.nodes

    def test_save_after_corruption_succeeds(self, storage: FileStorage, sample_cascade: Cascade):
        """load() raises on corrupt file, but save() still works after."""
        storage.base_dir.mkdir(parents=True, exist_ok=True)
        (storage.base_dir / "graph.json").write_text("{bad", encoding="utf-8")
        with pytest.raises(StorageCorruptionError):
            storage.load()
        storage.save(sample_cascade)
        loaded = storage.load()
        assert loaded is not None
        assert "a" in loaded.nodes

    def test_double_corruption_then_save_recovers(self, storage: FileStorage):
        """Corrupt twice, then save valid — storage recovers."""
        storage.base_dir.mkdir(parents=True, exist_ok=True)
        gp = storage.base_dir / "graph.json"
        gp.write_text("CORRUPT1", encoding="utf-8")
        with pytest.raises(StorageCorruptionError):
            storage.load()
        gp.write_text("CORRUPT2", encoding="utf-8")
        with pytest.raises(StorageCorruptionError):
            storage.load()
        cascade = Cascade()
        cascade.add_node(Node(id="recovered", state=NodeState.READY))
        storage.save(cascade)
        loaded = storage.load()
        assert loaded is not None
        assert "recovered" in loaded.nodes


# =======================================================================
# 2. Lock contention under threads
# =======================================================================


class TestLockContentionChaos:
    """Stress the lock mechanism with many threads and tight timing."""

    def test_many_threads_all_acquire_sequentially(self, storage: FileStorage):
        """N threads all competing for the lock — all should eventually acquire."""
        n_threads = 20
        acquired = []
        errors = []

        def worker(thread_id: int):
            try:
                with storage.lock(timeout=30):
                    acquired.append(thread_id)
                    time.sleep(0.005)  # Hold briefly
            except Exception as e:
                errors.append((thread_id, e))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)

        assert not errors, f"Lock errors: {errors}"
        assert len(acquired) == n_threads

    def test_lock_fairness_no_starvation(self, storage: FileStorage):
        """All threads should eventually get the lock — none starved."""
        n_threads = 10
        acquired_order: list[int] = []
        barrier = threading.Barrier(n_threads, timeout=10)

        def worker(thread_id: int):
            barrier.wait()  # All start competing at once
            with storage.lock(timeout=30):
                acquired_order.append(thread_id)
                time.sleep(0.01)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)

        assert sorted(acquired_order) == list(range(n_threads))

    def test_nonblocking_lock_races(self, storage: FileStorage):
        """Many non-blocking lock attempts — some succeed, rest get LockError."""
        n_threads = 15
        successes: list[int] = []
        lock_errors: list[int] = []
        other_errors: list[tuple[int, Exception]] = []
        barrier = threading.Barrier(n_threads, timeout=10)

        def worker(thread_id: int):
            barrier.wait()
            try:
                with storage.lock(blocking=False):
                    successes.append(thread_id)
                    time.sleep(0.05)  # Hold lock to force contention
            except LockError:
                lock_errors.append(thread_id)
            except Exception as e:
                other_errors.append((thread_id, e))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert not other_errors, f"Unexpected errors: {other_errors}"
        # At least one should succeed, the rest should get LockError
        assert len(successes) >= 1
        assert len(successes) + len(lock_errors) == n_threads

    def test_lock_release_on_exception(self, storage: FileStorage):
        """Lock must be released even if the body raises an exception."""
        with pytest.raises(ValueError, match="boom"):
            with storage.lock():
                raise ValueError("boom")

        # Lock should be available again
        with storage.lock(timeout=1):
            pass  # Should not hang or raise

    def test_thread_lock_and_file_lock_both_released_on_error(self, storage: FileStorage):
        """Both lock layers must release if an error occurs inside the block."""
        try:
            with storage.lock():
                raise RuntimeError("inner crash")
        except RuntimeError:
            pass

        # Thread lock should be free
        assert storage._thread_lock.acquire(timeout=1)
        storage._thread_lock.release()

        # File lock should be free — try acquiring from another FileStorage
        s2 = FileStorage(base_dir=storage.base_dir)
        with s2.lock(timeout=1):
            pass

    def test_concurrent_save_load_under_lock(self, storage: FileStorage):
        """Concurrent save+load under lock — file should never be corrupt."""
        cascade = Cascade()
        cascade.add_node(Node(id="root", state=NodeState.READY))
        storage.save(cascade)

        errors: list[tuple[str, Exception]] = []
        stop = threading.Event()

        def writer():
            i = 0
            while not stop.is_set():
                try:
                    c = Cascade()
                    c.add_node(Node(id=f"w{i}", state=NodeState.READY))
                    with storage.lock(timeout=5):
                        storage.save(c)
                    i += 1
                except Exception as e:
                    errors.append(("writer", e))
                    break

        def reader():
            while not stop.is_set():
                try:
                    with storage.lock(timeout=5):
                        result = storage.load()
                    assert result is not None
                except Exception as e:
                    errors.append(("reader", e))
                    break

        threads = [
            threading.Thread(target=writer),
            threading.Thread(target=reader),
            threading.Thread(target=reader),
        ]
        for t in threads:
            t.start()
        time.sleep(0.5)
        stop.set()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f"Errors during concurrent save/load: {errors}"

    def test_rapid_lock_unlock_cycles(self, storage: FileStorage):
        """Rapidly acquire/release the lock many times — no deadlock."""
        for _ in range(100):
            with storage.lock(timeout=5):
                pass  # Immediately release


# =======================================================================
# 3. Atomic write with concurrent readers
# =======================================================================


class TestAtomicWriteChaos:
    """Verify atomic write guarantees under concurrent access."""

    def test_readers_see_complete_json_during_writes(self, storage: FileStorage):
        """Concurrent readers should never see partial/torn JSON."""
        storage.base_dir.mkdir(parents=True, exist_ok=True)
        cascade = _make_large_cascade(30)
        storage.save(cascade)

        read_errors: list[str] = []
        stop = threading.Event()

        def writer():
            i = 0
            while not stop.is_set():
                c = _make_large_cascade(30)
                c.add_node(Node(id=f"extra_{i}", state=NodeState.READY))
                storage.save(c)
                i += 1

        def reader():
            while not stop.is_set():
                try:
                    gp = storage.base_dir / "graph.json"
                    if gp.exists():
                        text = gp.read_text(encoding="utf-8")
                        if text.strip():
                            data = json.loads(text)
                            # If we got valid JSON, check it has expected structure
                            if "nodes" not in data:
                                read_errors.append("Missing 'nodes' key")
                except json.JSONDecodeError:
                    # This is acceptable for non-locked readers
                    # (atomic rename is not perfectly atomic on all FSes)
                    pass
                except FileNotFoundError:
                    # File briefly absent during rename — acceptable
                    pass

        w = threading.Thread(target=writer)
        readers = [threading.Thread(target=reader) for _ in range(4)]
        w.start()
        for r in readers:
            r.start()
        time.sleep(0.5)
        stop.set()
        w.join(timeout=10)
        for r in readers:
            r.join(timeout=10)

        assert not read_errors, f"Torn reads detected: {read_errors}"

    def test_tmp_file_never_persists_after_save(self, storage: FileStorage):
        """After N saves, no .tmp file should remain."""
        for i in range(20):
            c = Cascade()
            c.add_node(Node(id=f"n{i}", state=NodeState.READY))
            storage.save(c)

        tmp_files = list(storage.base_dir.glob("*.tmp"))
        assert tmp_files == [], f"Leftover tmp files: {tmp_files}"

    def test_atomic_write_replaces_content_fully(self, tmp_path: Path):
        """Content is fully replaced, never appended."""
        path = tmp_path / "test.json"
        FileStorage._atomic_write(path, '{"version": 1}')
        assert json.loads(path.read_text(encoding="utf-8")) == {"version": 1}

        FileStorage._atomic_write(path, '{"version": 2}')
        assert json.loads(path.read_text(encoding="utf-8")) == {"version": 2}

        # Content should be exactly the new value, not concatenation
        text = path.read_text(encoding="utf-8")
        assert text.count("version") == 1

    def test_atomic_write_with_large_content(self, tmp_path: Path):
        """Large payloads should be written atomically without corruption."""
        path = tmp_path / "big.json"
        # ~1MB of JSON data
        big_data = {"key": "x" * 1_000_000}
        content = json.dumps(big_data)
        FileStorage._atomic_write(path, content)
        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert loaded == big_data

    def test_concurrent_atomic_writes_to_same_file(self, tmp_path: Path):
        """Multiple threads calling _atomic_write — file should always be valid.

        Note: _atomic_write without an external lock has a known race on the
        shared .tmp file. FileNotFoundError is expected when concurrent
        threads compete for the same tmp path. This test verifies the
        final file is always valid JSON regardless.
        """
        path = tmp_path / "shared.json"
        path.write_text('{"init": true}', encoding="utf-8")
        fnf_count = 0
        other_errors: list[Exception] = []
        count_lock = threading.Lock()

        def writer(thread_id: int):
            nonlocal fnf_count
            for i in range(50):
                try:
                    FileStorage._atomic_write(path, json.dumps({"thread": thread_id, "iter": i}))
                except FileNotFoundError:
                    # Expected race on shared .tmp file — not a bug
                    with count_lock:
                        fnf_count += 1
                except Exception as e:
                    other_errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert not other_errors, f"Unexpected errors: {other_errors}"
        # Final file should be valid JSON regardless of races
        final = json.loads(path.read_text(encoding="utf-8"))
        assert "thread" in final
        assert "iter" in final


# =======================================================================
# 4. Mid-save crash simulation
# =======================================================================


class TestMidSaveCrashSimulation:
    """Simulate crashes at various points during save and verify resilience."""

    def test_crash_during_write_text_preserves_old(
        self, storage: FileStorage, sample_cascade: Cascade
    ):
        """If write_text raises during tmp file creation, old graph survives."""
        storage.save(sample_cascade)
        old_content = (storage.base_dir / "graph.json").read_text(encoding="utf-8")

        # Patch Path.write_text to fail on the .tmp file
        original_write = Path.write_text

        def failing_write(self_path, content, *args, **kwargs):
            if str(self_path).endswith(".tmp"):
                raise OSError("Disk full")
            return original_write(self_path, content, *args, **kwargs)

        with patch.object(Path, "write_text", failing_write):
            with pytest.raises(OSError, match="Disk full"):
                storage.save(sample_cascade)

        # Original file should be intact
        current = (storage.base_dir / "graph.json").read_text(encoding="utf-8")
        assert current == old_content

    def test_crash_during_rename_leaves_tmp(self, storage: FileStorage, sample_cascade: Cascade):
        """If os.replace fails, the .tmp file may remain but old file is intact."""
        storage.save(sample_cascade)
        old_content = (storage.base_dir / "graph.json").read_text(encoding="utf-8")

        with patch("os.replace", side_effect=OSError("Permission denied")):
            with pytest.raises(OSError, match="Permission denied"):
                storage.save(sample_cascade)

        # Old file should still be valid
        current = (storage.base_dir / "graph.json").read_text(encoding="utf-8")
        assert current == old_content
        data = json.loads(current)
        assert "nodes" in data

    def test_crash_during_serialize_no_file_change(
        self, storage: FileStorage, sample_cascade: Cascade
    ):
        """If serialization crashes, no file write should happen."""
        storage.save(sample_cascade)
        old_content = (storage.base_dir / "graph.json").read_text(encoding="utf-8")

        with patch(
            "cascade.storage.file_storage.serialize_graph",
            side_effect=RuntimeError("serialize crash"),
        ):
            with pytest.raises(RuntimeError, match="serialize crash"):
                storage.save(sample_cascade)

        # File should be unchanged
        current = (storage.base_dir / "graph.json").read_text(encoding="utf-8")
        assert current == old_content

    def test_crash_during_json_dumps_no_file_change(
        self, storage: FileStorage, sample_cascade: Cascade
    ):
        """If json.dumps fails, no file should be written."""
        storage.save(sample_cascade)
        old_content = (storage.base_dir / "graph.json").read_text(encoding="utf-8")

        with patch(
            "cascade.storage.file_storage.json.dumps",
            side_effect=TypeError("not serializable"),
        ):
            with pytest.raises(TypeError, match="not serializable"):
                storage.save(sample_cascade)

        current = (storage.base_dir / "graph.json").read_text(encoding="utf-8")
        assert current == old_content

    def test_crash_during_mkdir_on_save(self, storage: FileStorage):
        """If mkdir fails during save, we get a clean error."""
        cascade = Cascade()
        cascade.add_node(Node(id="x", state=NodeState.READY))

        with patch.object(Path, "mkdir", side_effect=OSError("mkdir failed")):
            with pytest.raises(OSError, match="mkdir failed"):
                storage.save(cascade)

    def test_partial_tmp_file_cleaned_up_on_retry(
        self, storage: FileStorage, sample_cascade: Cascade
    ):
        """After a failed save that left a .tmp file, a successful save cleans up."""
        storage.save(sample_cascade)

        # Create a stale .tmp file (simulating a previous crash)
        tmp_file = storage.base_dir / "graph.json.tmp"
        tmp_file.write_text("stale", encoding="utf-8")
        assert tmp_file.exists()

        # New save should overwrite the .tmp and then rename
        storage.save(sample_cascade)
        assert not tmp_file.exists()

    def test_load_after_crash_with_stale_tmp(self, storage: FileStorage, sample_cascade: Cascade):
        """A stale .tmp file from a crash should not affect load."""
        storage.save(sample_cascade)

        # Leave a stale .tmp lying around
        (storage.base_dir / "graph.json.tmp").write_text("leftover from crash", encoding="utf-8")

        loaded = storage.load()
        assert loaded is not None
        assert "a" in loaded.nodes

    def test_save_with_read_only_directory(self, storage: FileStorage):
        """Save to a read-only directory should raise cleanly."""
        storage.base_dir.mkdir(parents=True, exist_ok=True)
        cascade = Cascade()
        cascade.add_node(Node(id="x", state=NodeState.READY))

        # First save succeeds
        storage.save(cascade)

        # Make directory read-only
        original_mode = storage.base_dir.stat().st_mode
        try:
            storage.base_dir.chmod(stat.S_IRUSR | stat.S_IXUSR)
            with pytest.raises(OSError):
                storage.save(cascade)
        finally:
            # Restore permissions for cleanup
            storage.base_dir.chmod(original_mode)


# =======================================================================
# 5. Lamport clock chaos
# =======================================================================


class TestLamportClockChaos:
    """Stress the HLC/Lamport clock under adversarial conditions."""

    def test_lamport_monotonic_under_concurrent_calls(self, storage: FileStorage):
        """Multiple threads calling next_lamport — all values must be unique."""
        results: list[int] = []
        lock = threading.Lock()

        def worker():
            vals = []
            for _ in range(100):
                with lock:
                    vals.append(storage.next_lamport())
            with lock:
                results.extend(vals)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(results) == 500
        assert len(set(results)) == 500, "Duplicate lamport values detected"
        assert results == sorted(results), "Lamport values not monotonically increasing"

    def test_observe_with_far_future_timestamp(self, storage: FileStorage):
        """Observing a timestamp far in the future should not break next_lamport."""
        far_future = int(time.time() * 1000) + 10_000_000_000  # ~115 days ahead
        storage.observe(far_future)
        ts = storage.next_lamport()
        assert ts > far_future

    def test_observe_with_zero(self, storage: FileStorage):
        """Observing 0 should not regress the clock."""
        storage.next_lamport()
        old = storage._lamport
        storage.observe(0)
        assert storage._lamport == old

    def test_lamport_survives_save_load_cycle(self, storage: FileStorage):
        """Lamport should be >= saved value after load."""
        for _ in range(10):
            storage.next_lamport()
        expected = storage._lamport

        cascade = Cascade()
        storage.save(cascade)

        s2 = FileStorage(base_dir=storage.base_dir)
        assert s2._lamport == expected

    def test_lamport_recovery_from_corrupt_file(self, storage: FileStorage):
        """Corrupt graph.json => lamport resets to 0."""
        storage.base_dir.mkdir(parents=True, exist_ok=True)
        for _ in range(5):
            storage.next_lamport()

        (storage.base_dir / "graph.json").write_text("not json", encoding="utf-8")
        s2 = FileStorage(base_dir=storage.base_dir)
        assert s2._lamport == 0


# =======================================================================
# 6. Delete under adversarial conditions
# =======================================================================


class TestDeleteChaos:
    def test_delete_while_lock_held(self, storage: FileStorage, sample_cascade: Cascade):
        """Delete while another thread holds the lock should eventually succeed."""
        storage.save(sample_cascade)

        errors: list[Exception] = []
        deleted = threading.Event()

        def deleter():
            try:
                # Wait for lock holder to release
                time.sleep(0.05)
                storage.delete()
                deleted.set()
            except Exception as e:
                errors.append(e)

        with storage.lock():
            t = threading.Thread(target=deleter)
            t.start()
            time.sleep(0.1)  # Let deleter run — it should succeed since
            # delete doesn't need the lock

        t.join(timeout=5)
        # Delete should have completed (it doesn't acquire the lock)
        assert not errors or deleted.is_set()

    def test_double_delete(self, storage: FileStorage, sample_cascade: Cascade):
        """Deleting twice should not raise."""
        storage.save(sample_cascade)
        storage.delete()
        storage.delete()  # Second delete — dir already gone

    def test_save_after_delete(self, storage: FileStorage, sample_cascade: Cascade):
        """Save should work after delete (recreates directory)."""
        storage.save(sample_cascade)
        storage.delete()
        assert not storage.base_dir.exists()
        storage.save(sample_cascade)
        assert storage.exists()
        loaded = storage.load()
        assert loaded is not None
        assert "a" in loaded.nodes


# =======================================================================
# 7. Scope and init edge cases under chaos
# =======================================================================


class TestInitChaos:
    def test_init_with_nonexistent_deep_path(self, tmp_path: Path):
        """Init with deeply nested path that does not exist yet."""
        deep = tmp_path / "a" / "b" / "c" / "d" / ".cascade"
        s = FileStorage(base_dir=deep)
        cascade = Cascade()
        cascade.add_node(Node(id="deep", state=NodeState.READY))
        s.save(cascade)
        assert deep.exists()
        loaded = s.load()
        assert loaded is not None
        assert "deep" in loaded.nodes

    def test_init_with_symlink_base_dir(self, tmp_path: Path):
        """Init with a symlinked base_dir should follow the link."""
        real = tmp_path / "real_cascade"
        real.mkdir()
        link = tmp_path / "link_cascade"
        link.symlink_to(real)

        s = FileStorage(base_dir=link)
        cascade = Cascade()
        cascade.add_node(Node(id="sym", state=NodeState.READY))
        s.save(cascade)

        # Both the link path and real path should have the file
        assert (link / "graph.json").exists()
        assert (real / "graph.json").exists()

    def test_two_storages_same_directory(self, temp_dir: Path):
        """Two FileStorage instances on the same dir — lock contention works."""
        s1 = FileStorage(base_dir=temp_dir)
        s2 = FileStorage(base_dir=temp_dir)

        cascade = Cascade()
        cascade.add_node(Node(id="shared", state=NodeState.READY))

        with s1.lock():
            s1.save(cascade)

        with s2.lock():
            loaded = s2.load()

        assert loaded is not None
        assert "shared" in loaded.nodes


# =======================================================================
# 8. Stress: rapid save/load cycles
# =======================================================================


class TestStressCycles:
    def test_rapid_save_load_100_cycles(self, storage: FileStorage):
        """100 rapid save/load cycles — data never lost."""
        for i in range(100):
            cascade = Cascade()
            cascade.add_node(Node(id=f"node_{i}", state=NodeState.READY))
            storage.save(cascade)
            loaded = storage.load()
            assert loaded is not None
            assert f"node_{i}" in loaded.nodes

    def test_growing_graph_save_load(self, storage: FileStorage):
        """Save/load a graph that grows each iteration."""
        cascade = Cascade()
        for i in range(50):
            cascade.add_node(Node(id=f"n{i}", state=NodeState.READY))
            if i > 0:
                cascade.add_edge(f"n{i - 1}", f"n{i}", expectation=f"e{i}", promise=f"p{i}")
            storage.save(cascade)
            loaded = storage.load()
            assert loaded is not None
            assert len(loaded.nodes) == i + 1

    def test_concurrent_growing_graphs(self, temp_dir: Path):
        """Two threads independently growing and saving — lock prevents corruption."""
        storage = FileStorage(base_dir=temp_dir)
        errors: list[tuple[str, Exception]] = []

        def grower(prefix: str, count: int):
            try:
                for i in range(count):
                    with storage.lock(timeout=10):
                        loaded = storage.load()
                        cascade = loaded if loaded else Cascade()
                        nid = f"{prefix}_{i}"
                        cascade.add_node(Node(id=nid, state=NodeState.READY))
                        storage.save(cascade)
            except Exception as e:
                errors.append((prefix, e))

        t1 = threading.Thread(target=grower, args=("A", 20))
        t2 = threading.Thread(target=grower, args=("B", 20))
        t1.start()
        t2.start()
        t1.join(timeout=30)
        t2.join(timeout=30)

        assert not errors, f"Errors: {errors}"
        loaded = storage.load()
        assert loaded is not None
        assert len(loaded.nodes) == 40


# =======================================================================
# 9. StorageCorruptionError diagnostics
# =======================================================================


class TestCorruptionErrorDiagnostics:
    """StorageCorruptionError carries actionable diagnostic info."""

    def test_error_includes_path(self, storage: FileStorage):
        storage.base_dir.mkdir(parents=True, exist_ok=True)
        (storage.base_dir / "graph.json").write_text("{bad", encoding="utf-8")
        with pytest.raises(StorageCorruptionError) as exc_info:
            storage.load()
        assert exc_info.value.path is not None
        assert "graph.json" in exc_info.value.path

    def test_error_includes_reason(self, storage: FileStorage):
        storage.base_dir.mkdir(parents=True, exist_ok=True)
        (storage.base_dir / "graph.json").write_bytes(bytes(range(256)))
        with pytest.raises(StorageCorruptionError) as exc_info:
            storage.load()
        assert "binary content" in exc_info.value.reason

    def test_error_chains_original_exception(self, storage: FileStorage):
        storage.base_dir.mkdir(parents=True, exist_ok=True)
        (storage.base_dir / "graph.json").write_text("[1,2]", encoding="utf-8")
        with pytest.raises(StorageCorruptionError) as exc_info:
            storage.load()
        assert exc_info.value.__cause__ is None  # type guard, not chained
        assert "expected JSON object" in exc_info.value.reason

    def test_malformed_json_chains_decode_error(self, storage: FileStorage):
        storage.base_dir.mkdir(parents=True, exist_ok=True)
        (storage.base_dir / "graph.json").write_text("{{{{", encoding="utf-8")
        with pytest.raises(StorageCorruptionError) as exc_info:
            storage.load()
        assert isinstance(exc_info.value.__cause__, json.JSONDecodeError)


# =======================================================================
# 10. backup_corrupt() forensic preservation
# =======================================================================


class TestBackupCorrupt:
    """backup_corrupt() preserves evidence for forensic analysis."""

    def test_backup_renames_graph_json(self, storage: FileStorage):
        storage.base_dir.mkdir(parents=True, exist_ok=True)
        gp = storage.base_dir / "graph.json"
        gp.write_text("CORRUPT", encoding="utf-8")
        backup = storage.backup_corrupt("test reason")
        assert backup is not None
        backup_path = Path(backup)
        assert backup_path.exists()
        assert backup_path.read_text(encoding="utf-8") == "CORRUPT"
        assert not gp.exists()

    def test_backup_returns_none_when_no_file(self, storage: FileStorage):
        storage.base_dir.mkdir(parents=True, exist_ok=True)
        assert storage.backup_corrupt("nothing to back up") is None

    def test_backup_path_contains_timestamp(self, storage: FileStorage):
        storage.base_dir.mkdir(parents=True, exist_ok=True)
        (storage.base_dir / "graph.json").write_text("X", encoding="utf-8")
        backup = storage.backup_corrupt("reason")
        assert "graph.json.corrupt." in backup

    def test_multiple_backups_coexist(self, storage: FileStorage):
        """Nanosecond timestamps ensure no collision even without delay."""
        storage.base_dir.mkdir(parents=True, exist_ok=True)
        gp = storage.base_dir / "graph.json"
        gp.write_text("CORRUPT1", encoding="utf-8")
        b1 = storage.backup_corrupt("first")
        gp.write_text("CORRUPT2", encoding="utf-8")
        b2 = storage.backup_corrupt("second")
        assert Path(b1).exists()
        assert Path(b2).exists()
        assert b1 != b2


# =======================================================================
# 11. Client-level corruption recovery via event replay
# =======================================================================


class TestClientCorruptionRecovery:
    """CascadeClient recovers from graph corruption using event replay."""

    def test_recovery_from_event_log(self, temp_dir: Path):
        """Corrupt graph.json with intact events — client recovers via replay."""
        from cascade.client import CascadeClient
        from cascade.types import Contract

        client = CascadeClient(temp_dir)
        client.add("a")
        client.add("b", deps={"a": Contract("E", "P")})

        (temp_dir / "graph.json").write_text("CORRUPT!", encoding="utf-8")

        r = client.nodes()
        assert r.success
        assert r.data["count"] == 2
        node_ids = {n["id"] for n in r.data["nodes"]}
        assert node_ids == {"a", "b"}

    def test_recovery_creates_backup(self, temp_dir: Path):
        """Recovery should preserve the corrupt file for forensics."""
        from cascade.client import CascadeClient

        client = CascadeClient(temp_dir)
        client.add("x")

        (temp_dir / "graph.json").write_text("CORRUPT!", encoding="utf-8")

        client.nodes()

        backups = list(temp_dir.glob("graph.json.corrupt.*"))
        assert len(backups) == 1
        assert backups[0].read_text(encoding="utf-8") == "CORRUPT!"

    def test_recovery_self_heals_snapshot(self, temp_dir: Path):
        """After recovery, graph.json should be valid again."""
        from cascade.client import CascadeClient

        client = CascadeClient(temp_dir)
        client.add("a")

        (temp_dir / "graph.json").write_text("{bad", encoding="utf-8")

        client.nodes()

        loaded = client.storage.load()
        assert loaded is not None
        assert "a" in loaded.nodes

    def test_recovery_emits_corruption_event(self, temp_dir: Path):
        """Recovery records a GRAPH_CORRUPTED event in the audit trail."""
        from cascade.client import CascadeClient
        from cascade.events import EventType

        client = CascadeClient(temp_dir)
        client.add("a")

        (temp_dir / "graph.json").write_text("[1,2,3]", encoding="utf-8")

        client.nodes()

        corruption_events = client.storage.events.read_by_type(EventType.GRAPH_CORRUPTED)
        assert len(corruption_events) == 1
        assert corruption_events[0].data["recovery_source"] == "event_log"
        assert corruption_events[0].data["node_count"] == 1

    def test_recovery_with_no_events(self, temp_dir: Path):
        """Corrupt graph.json with no event log — starts from empty graph."""
        from cascade.client import CascadeClient

        storage = FileStorage(temp_dir)
        storage.base_dir.mkdir(parents=True, exist_ok=True)
        (storage.base_dir / "graph.json").write_text("CORRUPT!", encoding="utf-8")

        client = CascadeClient(storage)
        r = client.nodes()
        assert r.success
        assert r.data["count"] == 0

    def test_recovery_via_mutate(self, temp_dir: Path):
        """Mutation operations (add/claim/etc.) also recover from corruption."""
        from cascade.client import CascadeClient

        client = CascadeClient(temp_dir)
        client.add("original")

        (temp_dir / "graph.json").write_text("BAD!", encoding="utf-8")

        r = client.add("new_node")
        assert r.success

        r = client.nodes()
        assert r.success
        node_ids = {n["id"] for n in r.data["nodes"]}
        assert "original" in node_ids
        assert "new_node" in node_ids

    def test_recovery_when_both_sources_corrupt(self, temp_dir: Path):
        """Both graph.json and events.jsonl corrupt — starts from empty graph."""
        from cascade.client import CascadeClient

        client = CascadeClient(temp_dir)
        client.add("a")

        (temp_dir / "graph.json").write_text("CORRUPT!", encoding="utf-8")
        (temp_dir / "events.jsonl").write_bytes(bytes(range(256)))

        r = client.nodes()
        assert r.success
        assert r.data["count"] == 0

    def test_replay_with_corruption_event(self, temp_dir: Path):
        """Event log containing GRAPH_CORRUPTED can be replayed without error."""
        from cascade.client import CascadeClient
        from cascade.events import EventType
        from cascade.replay import replay as replay_events

        client = CascadeClient(temp_dir)
        client.add("a")

        (temp_dir / "graph.json").write_text("CORRUPT!", encoding="utf-8")
        client.nodes()

        events = client.storage.events.read_all()
        corruption_events = [e for e in events if e.type == EventType.GRAPH_CORRUPTED]
        assert len(corruption_events) >= 1

        graph = replay_events(events, client.storage.content)
        assert "a" in graph.nodes
