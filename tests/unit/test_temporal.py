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

"""Tests for temporal query capabilities (show, diff, snapshot-at)."""

from pathlib import Path

import pytest

from cascade.client import CascadeClient
from cascade.types import Contract


@pytest.fixture
def client(tmp_path: Path) -> CascadeClient:
    return CascadeClient(tmp_path / ".cascade")


@pytest.fixture
def populated_client(client: CascadeClient) -> CascadeClient:
    """A client with a small DAG and some completed tasks."""
    client.add("analyze")
    client.add("design", deps={"analyze": Contract("need spec", "deliver spec")})
    client.add("impl", deps={"design": Contract("need design", "deliver code")})

    r = client.claim("agent-1")
    assert r.data["task_id"] == "analyze"
    _t = r.data["token"]
    client.complete(
        "analyze",
        agent_id="agent-1",
        summary="analyzed requirements",
        critical={"lang": "python"},
        artifacts="full analysis document",
        token=_t,
    )

    r = client.claim("agent-2")
    assert r.data["task_id"] == "design"
    _t = r.data["token"]
    client.complete(
        "design",
        agent_id="agent-2",
        summary="designed API",
        artifacts="API specification v1",
        token=_t,
    )
    return client


def _all_ts(client: CascadeClient) -> list[int]:
    """Get all logical timestamps from event log, sorted."""
    events = client.storage.events.read_all()
    return sorted(e.logical_ts for e in events if e.logical_ts)


class TestShow:
    def test_show_existing_event(self, populated_client: CascadeClient):
        ts = _all_ts(populated_client)[0]
        r = populated_client.show(ts)
        assert r.success
        assert r.data["logical_ts"] == ts
        assert r.data["type"] is not None

    def test_show_nonexistent(self, populated_client: CascadeClient):
        r = populated_client.show(9999)
        assert not r.success

    def test_show_resolves_artifacts(self, populated_client: CascadeClient):
        r = populated_client.history()
        completed_events = [e for e in r.data["events"] if e["type"] == "task_completed"]
        assert len(completed_events) >= 1

        ts = completed_events[0]["logical_ts"]
        r = populated_client.show(ts)
        assert r.success
        ctx = r.data["data"].get("context", {})
        if "artifacts_ref" in ctx:
            assert "artifacts_content" in ctx


class TestDiff:
    def test_diff_range(self, populated_client: CascadeClient):
        ts_list = _all_ts(populated_client)
        r = populated_client.diff(ts_list[0], ts_list[-1])
        assert r.success
        assert r.data["count"] >= 1
        assert len(r.data["nodes_changed"]) >= 1

    def test_diff_full_range(self, populated_client: CascadeClient):
        ts_list = _all_ts(populated_client)
        r = populated_client.diff(ts_list[0], ts_list[-1])
        assert r.success
        assert "analyze" in r.data["nodes_changed"]
        assert "design" in r.data["nodes_changed"]

    def test_diff_empty_range(self, populated_client: CascadeClient):
        r = populated_client.diff(9000, 9999)
        assert r.success
        assert r.data["count"] == 0

    def test_diff_invalid_range(self, populated_client: CascadeClient):
        r = populated_client.diff(10, 1)
        assert not r.success

    def test_diff_single_point(self, populated_client: CascadeClient):
        ts = _all_ts(populated_client)[0]
        r = populated_client.diff(ts, ts)
        assert r.success
        assert r.data["count"] == 1


class TestSnapshotAt:
    def test_snapshot_after_first_add(self, populated_client: CascadeClient):
        ts = _all_ts(populated_client)[0]
        r = populated_client.snapshot_at(ts)
        assert r.success
        assert r.data["node_count"] >= 1

    def test_snapshot_after_all_events(self, populated_client: CascadeClient):
        ts = _all_ts(populated_client)[-1]
        r = populated_client.snapshot_at(ts)
        assert r.success
        assert r.data["node_count"] == 3
        node_ids = {n["id"] for n in r.data["nodes"]}
        assert node_ids == {"analyze", "design", "impl"}

    def test_snapshot_nonexistent_ts(self, populated_client: CascadeClient):
        r = populated_client.snapshot_at(0)
        assert not r.success

    def test_snapshot_shows_intermediate_state(self, populated_client: CascadeClient):
        r = populated_client.history()
        events = r.data["events"]

        add_events = [e for e in events if e["type"] == "node_added"]
        first_add_ts = add_events[0]["logical_ts"]

        r = populated_client.snapshot_at(first_add_ts)
        assert r.success
        assert r.data["node_count"] < 3


class TestEventStoreQueries:
    def test_read_at(self, populated_client: CascadeClient):
        ts = _all_ts(populated_client)[0]
        event = populated_client.storage.events.read_at(ts)
        assert event is not None
        assert event.logical_ts == ts

    def test_read_at_missing(self, populated_client: CascadeClient):
        event = populated_client.storage.events.read_at(9999)
        assert event is None

    def test_read_range(self, populated_client: CascadeClient):
        ts_list = _all_ts(populated_client)
        events = populated_client.storage.events.read_range(ts_list[0], ts_list[2])
        assert all(ts_list[0] <= e.logical_ts <= ts_list[2] for e in events)

    def test_read_until(self, populated_client: CascadeClient):
        ts_list = _all_ts(populated_client)
        events = populated_client.storage.events.read_until(ts_list[1])
        assert all(e.logical_ts <= ts_list[1] for e in events)
        assert len(events) >= 1
