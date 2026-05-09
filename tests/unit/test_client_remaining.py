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

"""Tests for remaining uncovered client.py branches.

Covers: rework parameter validation, history event_type validation,
and _update_context merge modes.
"""

from __future__ import annotations

import pytest
from conftest import auto_deliverables, claim_token

from cascade.client import CascadeClient
from cascade.types import Contract, ErrorCode

# ---------------------------------------------------------------------------
# rework() parameter validation
# ---------------------------------------------------------------------------


class TestReworkValidation:
    @pytest.mark.parametrize(
        "missing_field",
        [
            "corrective",
            "reason",
            "agent_id",
            "source_expectation",
            "source_promise",
            "corrective_expectation",
            "corrective_promise",
        ],
    )
    def test_rework_missing_required_field(self, client: CascadeClient, missing_field):
        client.add("a")
        client.add("b", deps={"a": Contract("E", "P")})
        _t = claim_token(client, "w1", "a")
        client.complete("a", token=_t, summary="done", deliverables=auto_deliverables(client, "a"))
        client.claim("w2", "b")

        params = {
            "source": "a",
            "corrective": "a-fix",
            "reason": "wrong",
            "agent_id": "w2",
            "source_expectation": "se",
            "source_promise": "sp",
            "corrective_expectation": "ce",
            "corrective_promise": "cp",
        }
        params[missing_field] = ""
        r = client.rework(**params)
        assert not r.success
        assert r.code == ErrorCode.INVALID_INPUT
        assert missing_field in r.message.lower()


# ---------------------------------------------------------------------------
# history() event_type validation
# ---------------------------------------------------------------------------


class TestHistoryValidation:
    def test_invalid_event_type(self, client: CascadeClient):
        client.add("a")
        r = client.history(event_type="NONEXISTENT_TYPE")
        assert not r.success
        assert r.code == ErrorCode.INVALID_INPUT
        assert "Invalid event_type" in r.message

    def test_valid_event_type(self, client: CascadeClient):
        client.add("a")
        r = client.history(event_type="node_added")
        assert r.success
        assert r.data["count"] >= 1

    def test_history_by_node(self, client: CascadeClient):
        client.add("a")
        client.add("b")
        r = client.history(node_id="a")
        assert r.success
        for event in r.data.get("events", []):
            assert event["data"].get("node_id") == "a"

    def test_history_last_n(self, client: CascadeClient):
        client.add("a")
        client.add("b")
        client.add("c")
        r = client.history(last_n=1)
        assert r.success
        assert r.data["count"] == 1


# ---------------------------------------------------------------------------
# _update_context merge modes
# ---------------------------------------------------------------------------


class TestContextMergeModes:
    def test_replace_mode(self, client: CascadeClient):
        client.add("a")
        client.edit("a", summary="first", critical={"k1": "v1"})
        client.edit(
            "a",
            summary="replaced",
            critical={"k2": "v2"},
            context_merge="replace",
        )
        with client.storage.lock():
            graph = client.storage.load()
        ctx = graph.nodes["a"].context
        assert ctx.summary == "replaced"
        assert ctx.critical == {"k2": "v2"}

    def test_append_mode_summary(self, client: CascadeClient):
        client.add("a")
        client.edit("a", summary="first")
        client.edit("a", summary="second", context_merge="append")
        with client.storage.lock():
            graph = client.storage.load()
        ctx = graph.nodes["a"].context
        assert "first" in ctx.summary
        assert "second" in ctx.summary

    def test_append_mode_critical_merges(self, client: CascadeClient):
        client.add("a")
        client.edit("a", critical={"k1": "v1"})
        client.edit("a", critical={"k2": "v2"}, context_merge="append")
        with client.storage.lock():
            graph = client.storage.load()
        ctx = graph.nodes["a"].context
        assert ctx.critical == {"k1": "v1", "k2": "v2"}

    def test_merge_mode_default(self, client: CascadeClient):
        client.add("a")
        client.edit("a", summary="first", critical={"k1": "v1"})
        client.edit("a", summary="second", critical={"k2": "v2"})
        with client.storage.lock():
            graph = client.storage.load()
        ctx = graph.nodes["a"].context
        assert "first" in ctx.summary
        assert "second" in ctx.summary
        assert ctx.critical == {"k1": "v1", "k2": "v2"}

    def test_no_context_updates_returns_no_change(self, client: CascadeClient):
        client.add("a")
        r = client.edit("a")
        assert r.success
        assert "No changes" in r.message

    def test_context_created_when_none(self, client: CascadeClient):
        client.add("a")
        client.edit("a", summary="new context")
        with client.storage.lock():
            graph = client.storage.load()
        assert graph.nodes["a"].context is not None
        assert graph.nodes["a"].context.summary == "new context"
