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


class TestContextFlow:
    """Tests that agent output flows through the DAG."""

    def test_summary_propagates_to_child(self, temp_storage):
        """Agent A's summary is visible to agent B."""
        add_node.add_node(temp_storage, {"node_id": "a"})
        add_node.add_node(temp_storage, {
            "node_id": "b",
            "dependencies": ["a"],
            "expectations": [make_contract("a")],
        })

        # Agent 1 claims and completes A with output
        get_task.get_task(temp_storage, {"agent_id": "agent-1", "task_id": "a"})
        finish_task.finish_task(temp_storage, {
            "task_id": "a",
            "success": True,
            "summary": "Analysis found 3 API endpoints",
        })

        # Agent 2 claims B — should see A's output
        result = get_task.get_task(temp_storage, {"agent_id": "agent-2", "task_id": "b"})
        task_info = result["data"]["task_info"]

        assert "context" in task_info
        assert "Analysis found 3 API endpoints" in task_info["context"]["summary"]

    def test_critical_propagates_indefinitely(self, temp_storage):
        """Critical KV data propagates through the entire chain."""
        add_node.add_node(temp_storage, {"node_id": "a"})
        add_node.add_node(temp_storage, {
            "node_id": "b",
            "dependencies": ["a"],
            "expectations": [make_contract("a")],
        })
        add_node.add_node(temp_storage, {
            "node_id": "c",
            "dependencies": ["b"],
            "expectations": [make_contract("b")],
        })

        # A completes with critical data
        get_task.get_task(temp_storage, {"agent_id": "agent-1", "task_id": "a"})
        finish_task.finish_task(temp_storage, {
            "task_id": "a",
            "success": True,
            "summary": "Found endpoints",
            "critical": {"api_endpoints": ["/users", "/auth"], "schema_version": 2},
        })

        # B completes, adding its own critical data
        get_task.get_task(temp_storage, {"agent_id": "agent-2", "task_id": "b"})
        finish_task.finish_task(temp_storage, {
            "task_id": "b",
            "success": True,
            "summary": "Implementation done",
            "critical": {"implementation_lang": "python"},
        })

        # C should see critical data from BOTH A and B
        result = get_task.get_task(temp_storage, {"agent_id": "agent-3", "task_id": "c"})
        task_info = result["data"]["task_info"]

        assert task_info["context"]["critical"]["api_endpoints"] == ["/users", "/auth"]
        assert task_info["context"]["critical"]["schema_version"] == 2
        assert task_info["context"]["critical"]["implementation_lang"] == "python"

    def test_context_created_when_none(self, temp_storage):
        """finish_task creates context if node has none — no silent dropping."""
        add_node.add_node(temp_storage, {"node_id": "a"})

        get_task.get_task(temp_storage, {"agent_id": "agent-1", "task_id": "a"})
        finish_task.finish_task(temp_storage, {
            "task_id": "a",
            "success": True,
            "summary": "This must not be silently dropped",
        })

        with temp_storage.lock():
            cascade = temp_storage.load()
            assert cascade.nodes["a"].context is not None
            assert cascade.nodes["a"].context.summary == "This must not be silently dropped"

    def test_diamond_context_merge(self, temp_storage):
        """Context from parallel branches merges at the join node."""
        #   a
        #  / \
        # b   c
        #  \ /
        #   d
        add_node.add_node(temp_storage, {"node_id": "a"})
        add_node.add_node(temp_storage, {
            "node_id": "b", "dependencies": ["a"],
            "expectations": [make_contract("a")],
        })
        add_node.add_node(temp_storage, {
            "node_id": "c", "dependencies": ["a"],
            "expectations": [make_contract("a")],
        })
        add_node.add_node(temp_storage, {
            "node_id": "d", "dependencies": ["b", "c"],
            "expectations": [make_contract("b"), make_contract("c")],
        })

        # Complete a
        get_task.get_task(temp_storage, {"agent_id": "a1", "task_id": "a"})
        finish_task.finish_task(temp_storage, {
            "task_id": "a",
            "success": True,
            "critical": {"root_data": "shared"},
        })

        # Complete b and c with different outputs
        get_task.get_task(temp_storage, {"agent_id": "a2", "task_id": "b"})
        finish_task.finish_task(temp_storage, {
            "task_id": "b",
            "success": True,
            "summary": "Branch B done",
            "critical": {"branch": "B"},
        })

        get_task.get_task(temp_storage, {"agent_id": "a3", "task_id": "c"})
        finish_task.finish_task(temp_storage, {
            "task_id": "c",
            "success": True,
            "summary": "Branch C done",
            "critical": {"branch": "C"},  # overwrites B's "branch" key — latest wins
        })

        # D should see merged context from all ancestors
        result = get_task.get_task(temp_storage, {"agent_id": "a4", "task_id": "d"})
        ctx = result["data"]["task_info"]["context"]

        assert ctx["critical"]["root_data"] == "shared"  # from a
        assert "Branch B done" in ctx["summary"] or "Branch C done" in ctx["summary"]

    def test_backward_compat_result_param(self, temp_storage):
        """'result' param still works as alias for 'summary'."""
        add_node.add_node(temp_storage, {"node_id": "a"})
        add_node.add_node(temp_storage, {
            "node_id": "b", "dependencies": ["a"],
            "expectations": [make_contract("a")],
        })

        get_task.get_task(temp_storage, {"agent_id": "a1", "task_id": "a"})
        finish_task.finish_task(temp_storage, {
            "task_id": "a",
            "success": True,
            "result": "Old-style result param",  # not 'summary'
        })

        result = get_task.get_task(temp_storage, {"agent_id": "a2", "task_id": "b"})
        assert "Old-style result param" in result["data"]["task_info"]["context"]["summary"]
