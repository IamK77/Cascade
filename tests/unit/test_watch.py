"""Tests for `cascade watch` — streaming state transitions.

Watch is a long-running CLI subprocess; tests spawn it, drive state
changes via the Python API, then read transitions from its stdout.
"""

import json
import subprocess
import sys
import time

import pytest

from cascade import CascadeClient, Contract  # noqa: F401


@pytest.fixture
def storage_dir(tmp_path):
    return tmp_path / ".cascade"


@pytest.fixture
def client(storage_dir):
    return CascadeClient(str(storage_dir))


def _start_watch(storage_dir):
    """Spawn `cascade watch` as a subprocess; return (proc, stdout_iter)."""
    proc = subprocess.Popen(
        [sys.executable, "-m", "cascade.cli", "--storage", str(storage_dir), "watch"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    return proc


def _drain_then_terminate(proc, settle_seconds=1.0):
    """Wait for watch to flush pending output, then terminate and read all stdout.

    Watch is event-driven; tests trigger state changes, then this helper sleeps
    long enough for those changes to be detected and emitted, then collects the
    full output via communicate().
    """
    time.sleep(settle_seconds)
    proc.terminate()
    out, _ = proc.communicate(timeout=3)
    return [line for line in out.splitlines() if line.strip()]


class TestWatch:
    def test_emits_claim_transition(self, client, storage_dir):
        client.add("a")
        proc = _start_watch(storage_dir)
        time.sleep(0.3)  # let watch baseline
        client.claim("w1", "a")
        lines = _drain_then_terminate(proc)
        assert len(lines) == 1
        t = json.loads(lines[0])
        assert t["node"] == "a"
        assert t["from"] == "READY"
        assert t["to"] == "ACTIVE"
        assert t["agent"] == "w1"

    def test_emits_completion_and_unblocks(self, client, storage_dir):
        client.add("up")
        client.add("down", deps={"up": Contract("E", "P")})
        client.claim("w1", "up")
        proc = _start_watch(storage_dir)
        time.sleep(0.3)
        client.complete("up", summary="ok")
        lines = _drain_then_terminate(proc)
        transitions = [json.loads(line) for line in lines]
        states = {t["node"]: (t["from"], t["to"]) for t in transitions}
        assert states["up"] == ("ACTIVE", "COMPLETED")
        assert states["down"] == ("PENDING", "READY")

    def test_no_baseline_emit(self, client, storage_dir):
        client.add("a")
        client.add("b")
        proc = _start_watch(storage_dir)
        # No state changes after watch started — should be silent
        lines = _drain_then_terminate(proc, settle_seconds=0.5)
        assert lines == []

    def test_new_node_emits_null_to_state(self, client, storage_dir):
        client.add("first")  # baseline
        proc = _start_watch(storage_dir)
        time.sleep(0.3)
        client.add("second")
        lines = _drain_then_terminate(proc)
        assert len(lines) == 1
        t = json.loads(lines[0])
        assert t["node"] == "second"
        assert t["from"] is None
        assert t["to"] == "READY"
