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

from tools import add_node, finish_task, get_task


def make_contract(node_id: str) -> dict:
    return {
        "node_id": node_id,
        "expectation": f"Expect output from {node_id}",
        "promise": "Promise output to dependent",
    }


def find_entry(upstream: list, node_id: str) -> dict:
    """Find an upstream entry by node_id."""
    return next(e for e in upstream if e["node_id"] == node_id)


class TestContextFlow:
    """Tests that agent output flows through the DAG."""

    def test_summary_propagates_to_child(self, temp_storage):
        """Agent A's summary is visible to agent B."""
        add_node.add_node(temp_storage, {"node_id": "a"})
        add_node.add_node(
            temp_storage,
            {
                "node_id": "b",
                "dependencies": ["a"],
                "expectations": [make_contract("a")],
            },
        )

        get_task.get_task(temp_storage, {"agent_id": "agent-1", "task_id": "a"})
        finish_task.finish_task(
            temp_storage,
            {
                "task_id": "a",
                "success": True,
                "summary": "Analysis found 3 API endpoints",
            },
        )

        result = get_task.get_task(temp_storage, {"agent_id": "agent-2", "task_id": "b"})
        task_info = result["data"]["task_info"]

        assert "upstream" in task_info
        up = task_info["upstream"]
        assert len(up) == 1
        assert up[0]["node_id"] == "a"
        assert up[0]["distance"] == 1
        assert up[0]["expectation"] == "Expect output from a"
        assert up[0]["delivered"]["summary"] == "Analysis found 3 API endpoints"

    def test_critical_propagates_indefinitely(self, temp_storage):
        """Critical KV data propagates through the entire chain."""
        add_node.add_node(temp_storage, {"node_id": "a"})
        add_node.add_node(
            temp_storage,
            {
                "node_id": "b",
                "dependencies": ["a"],
                "expectations": [make_contract("a")],
            },
        )
        add_node.add_node(
            temp_storage,
            {
                "node_id": "c",
                "dependencies": ["b"],
                "expectations": [make_contract("b")],
            },
        )

        get_task.get_task(temp_storage, {"agent_id": "agent-1", "task_id": "a"})
        finish_task.finish_task(
            temp_storage,
            {
                "task_id": "a",
                "success": True,
                "summary": "Found endpoints",
                "critical": {"api_endpoints": ["/users", "/auth"], "schema_version": 2},
            },
        )

        get_task.get_task(temp_storage, {"agent_id": "agent-2", "task_id": "b"})
        finish_task.finish_task(
            temp_storage,
            {
                "task_id": "b",
                "success": True,
                "summary": "Implementation done",
                "critical": {"implementation_lang": "python"},
            },
        )

        result = get_task.get_task(temp_storage, {"agent_id": "agent-3", "task_id": "c"})
        up = result["data"]["task_info"]["upstream"]

        b_entry = find_entry(up, "b")
        a_entry = find_entry(up, "a")
        assert b_entry["distance"] == 1
        assert b_entry["delivered"]["critical"]["implementation_lang"] == "python"
        assert a_entry["distance"] == 2
        assert a_entry["path"] == ["a", "b"]
        assert a_entry["delivered"]["critical"]["api_endpoints"] == ["/users", "/auth"]
        assert len(up) == 2

    def test_context_created_when_none(self, temp_storage):
        """finish_task creates context if node has none — no silent dropping."""
        add_node.add_node(temp_storage, {"node_id": "a"})

        get_task.get_task(temp_storage, {"agent_id": "agent-1", "task_id": "a"})
        finish_task.finish_task(
            temp_storage,
            {
                "task_id": "a",
                "success": True,
                "summary": "This must not be silently dropped",
            },
        )

        with temp_storage.lock():
            cascade = temp_storage.load()
            assert cascade.nodes["a"].context is not None
            assert cascade.nodes["a"].context.summary == "This must not be silently dropped"

    def test_diamond_context_no_overwrite(self, temp_storage):
        """Context from parallel branches kept separate at the join node."""
        #   a
        #  / \
        # b   c
        #  \ /
        #   d
        add_node.add_node(temp_storage, {"node_id": "a"})
        add_node.add_node(
            temp_storage,
            {
                "node_id": "b",
                "dependencies": ["a"],
                "expectations": [make_contract("a")],
            },
        )
        add_node.add_node(
            temp_storage,
            {
                "node_id": "c",
                "dependencies": ["a"],
                "expectations": [make_contract("a")],
            },
        )
        add_node.add_node(
            temp_storage,
            {
                "node_id": "d",
                "dependencies": ["b", "c"],
                "expectations": [make_contract("b"), make_contract("c")],
            },
        )

        get_task.get_task(temp_storage, {"agent_id": "a1", "task_id": "a"})
        finish_task.finish_task(
            temp_storage,
            {
                "task_id": "a",
                "success": True,
                "critical": {"root_data": "shared"},
            },
        )

        get_task.get_task(temp_storage, {"agent_id": "a2", "task_id": "b"})
        finish_task.finish_task(
            temp_storage,
            {
                "task_id": "b",
                "success": True,
                "summary": "Branch B done",
                "critical": {"branch": "B"},
            },
        )

        get_task.get_task(temp_storage, {"agent_id": "a3", "task_id": "c"})
        finish_task.finish_task(
            temp_storage,
            {
                "task_id": "c",
                "success": True,
                "summary": "Branch C done",
                "critical": {"branch": "C"},
            },
        )

        result = get_task.get_task(temp_storage, {"agent_id": "a4", "task_id": "d"})
        up = result["data"]["task_info"]["upstream"]

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

    def test_backward_compat_result_param(self, temp_storage):
        """'result' param still works as alias for 'summary'."""
        add_node.add_node(temp_storage, {"node_id": "a"})
        add_node.add_node(
            temp_storage,
            {
                "node_id": "b",
                "dependencies": ["a"],
                "expectations": [make_contract("a")],
            },
        )

        get_task.get_task(temp_storage, {"agent_id": "a1", "task_id": "a"})
        finish_task.finish_task(
            temp_storage,
            {
                "task_id": "a",
                "success": True,
                "result": "Old-style result param",
            },
        )

        result = get_task.get_task(temp_storage, {"agent_id": "a2", "task_id": "b"})
        up = result["data"]["task_info"]["upstream"]
        assert up[0]["delivered"]["summary"] == "Old-style result param"
