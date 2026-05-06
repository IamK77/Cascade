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

"""Tests for end-to-end context flow between agents.

The most critical integration test: does an agent's output actually
reach downstream agents through context propagation?
"""

from cascade.client import CascadeClient
from cascade.types import Contract, TaskView


def find_entry(upstream: list, node_id: str) -> dict:
    """Find an upstream entry by node_id."""
    return next(e for e in upstream if e["node_id"] == node_id)


class TestContextFlow:
    """Tests that agent output flows through the DAG."""

    def test_summary_propagates_to_child(self, client: CascadeClient):
        """Agent A's summary is visible to agent B."""
        client.add("a")
        client.add(
            "b",
            deps={"a": Contract("Expect output from a", "Promise output to dependent")},
        )

        client.claim("agent-1", "a")
        client.complete("a", summary="Analysis found 3 API endpoints")

        task = TaskView.from_result(client.claim("agent-2", "b"))
        up = task.upstream

        assert len(up) == 1
        assert up[0]["node_id"] == "a"
        assert up[0]["distance"] == 1
        assert up[0]["expectation"] == "Expect output from a"
        assert up[0]["delivered"]["summary"] == "Analysis found 3 API endpoints"

    def test_critical_propagates_indefinitely(self, client: CascadeClient):
        """Critical KV data propagates through the entire chain."""
        client.add("a")
        client.add(
            "b",
            deps={"a": Contract("Expect output from a", "Promise output to dependent")},
        )
        client.add(
            "c",
            deps={"b": Contract("Expect output from b", "Promise output to dependent")},
        )

        client.claim("agent-1", "a")
        client.complete(
            "a",
            summary="Found endpoints",
            critical={"api_endpoints": ["/users", "/auth"], "schema_version": 2},
        )

        client.claim("agent-2", "b")
        client.complete(
            "b",
            summary="Implementation done",
            critical={"implementation_lang": "python"},
        )

        task = TaskView.from_result(client.claim("agent-3", "c"))
        up = task.upstream

        b_entry = find_entry(up, "b")
        a_entry = find_entry(up, "a")
        assert b_entry["distance"] == 1
        assert b_entry["delivered"]["critical"]["implementation_lang"] == "python"
        assert a_entry["distance"] == 2
        assert a_entry["path"] == ["a", "b"]
        assert a_entry["delivered"]["critical"]["api_endpoints"] == ["/users", "/auth"]
        assert len(up) == 2

    def test_context_created_when_none(self, client: CascadeClient, temp_storage):
        """finish_task creates context if node has none -- no silent dropping."""
        client.add("a")

        client.claim("agent-1", "a")
        client.complete("a", summary="This must not be silently dropped")

        with temp_storage.lock():
            cascade = temp_storage.load()
            assert cascade.nodes["a"].context is not None
            assert cascade.nodes["a"].context.summary == "This must not be silently dropped"

    def test_diamond_context_no_overwrite(self, client: CascadeClient):
        """Context from parallel branches kept separate at the join node."""
        #   a
        #  / \
        # b   c
        #  \ /
        #   d
        client.add("a")
        client.add(
            "b",
            deps={"a": Contract("Expect output from a", "Promise output to dependent")},
        )
        client.add(
            "c",
            deps={"a": Contract("Expect output from a", "Promise output to dependent")},
        )
        client.add(
            "d",
            deps={
                "b": Contract("Expect output from b", "Promise output to dependent"),
                "c": Contract("Expect output from c", "Promise output to dependent"),
            },
        )

        client.claim("a1", "a")
        client.complete("a", critical={"root_data": "shared"})

        client.claim("a2", "b")
        client.complete("b", summary="Branch B done", critical={"branch": "B"})

        client.claim("a3", "c")
        client.complete("c", summary="Branch C done", critical={"branch": "C"})

        task = TaskView.from_result(client.claim("a4", "d"))
        up = task.upstream

        b_entry = find_entry(up, "b")
        c_entry = find_entry(up, "c")
        assert b_entry["distance"] == 1
        assert b_entry["delivered"]["critical"]["branch"] == "B"
        assert c_entry["distance"] == 1
        assert c_entry["delivered"]["critical"]["branch"] == "C"

        a_entries = [e for e in up if e["node_id"] == "a"]
        assert len(a_entries) == 1
        assert a_entries[0]["distance"] == 2
        assert a_entries[0]["delivered"]["critical"]["root_data"] == "shared"

    def test_summary_as_summary_param(self, client: CascadeClient):
        """'summary' param works correctly."""
        client.add("a")
        client.add(
            "b",
            deps={"a": Contract("Expect output from a", "Promise output to dependent")},
        )

        client.claim("a1", "a")
        client.complete("a", summary="Old-style result param")

        task = TaskView.from_result(client.claim("a2", "b"))
        up = task.upstream
        assert up[0]["delivered"]["summary"] == "Old-style result param"
