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

"""Tests for LLM tools."""

import pytest

from cascade.core.cascade import Cascade
from cascade.core.state import NodeState
from cascade.storage.graph_storage import GraphStorage

from tools import (
    add_node,
    finish_task,
    get_task,
    list_nodes,
    refine_node,
    remove_node,
    split_node,
    execute_tool,
)


def make_contract(node_id: str, expectation: str = "", promise: str = "") -> dict:
    """Helper to create contract for tests."""
    return {
        "node_id": node_id,
        "expectation": expectation or f"Expect output from {node_id}",
        "promise": promise or f"Promise output to dependent",
    }


class TestGetTask:
    """Tests for get_task tool."""

    def test_get_any_task(self, temp_storage):
        # Add a ready task first
        add_node.add_node(temp_storage, {
            "node_id": "task_a",
        })
        # Add a pending task
        add_node.add_node(temp_storage, {
            "node_id": "task_b",
            "dependencies": ["task_a"],
            "expectations": [make_contract("task_a")],
        })

        result = get_task.get_task(temp_storage, {"agent_id": "agent_1"})
        assert result["success"] is True
        assert result["data"]["state"] == "ACTIVE"
        assert "task_info" in result["data"]

    def test_get_specific_task(self, temp_storage):
        add_node.add_node(temp_storage, {
            "node_id": "task_a",
        })

        result = get_task.get_task(temp_storage, {"task_id": "task_a", "agent_id": "agent_1"})
        assert result["success"] is True

        # Verify it's ACTIVE
        with temp_storage.lock():
            cascade = temp_storage.load()
            assert cascade.nodes["task_a"].state == NodeState.ACTIVE

    def test_get_task_not_ready(self, temp_storage):
        add_node.add_node(temp_storage, {
            "node_id": "task_a",
        })
        add_node.add_node(temp_storage, {
            "node_id": "task_b",
            "dependencies": ["task_a"],
            "expectations": [make_contract("task_a")],
        })

        result = get_task.get_task(temp_storage, {"task_id": "task_b", "agent_id": "agent_1"})
        assert result["success"] is False

    def test_agent_tracking(self, temp_storage):
        # Create a chain: root -> task_a, root -> task_b
        add_node.add_node(temp_storage, {"node_id": "root"})
        add_node.add_node(temp_storage, {
            "node_id": "task_a",
            "dependencies": ["root"],
            "expectations": [make_contract("root")],
        })
        add_node.add_node(temp_storage, {
            "node_id": "task_b",
            "dependencies": ["root"],
            "expectations": [make_contract("root")],
        })

        # Agent 1 gets a task
        result1 = get_task.get_task(temp_storage, {"agent_id": "agent_1"})
        assert result1["success"] is True

        # Agent 1 tries to get another task - should return reminder
        result2 = get_task.get_task(temp_storage, {"agent_id": "agent_1"})
        assert result2["success"] is True
        assert result2["data"].get("reminder") is True

    def test_no_available_tasks(self, temp_storage):
        # Add a task and complete it
        add_node.add_node(temp_storage, {"node_id": "task_a"})
        get_task.get_task(temp_storage, {"agent_id": "agent_1"})
        finish_task.finish_task(temp_storage, {"task_id": "task_a", "success": True})

        # Now try to get a task
        result = get_task.get_task(temp_storage, {"agent_id": "agent_2"})
        assert result["success"] is False

    def test_agent_id_required(self, temp_storage):
        add_node.add_node(temp_storage, {"node_id": "task_a"})

        result = get_task.get_task(temp_storage, {})
        assert result["success"] is False
        assert "agent_id is required" in result["message"]


class TestFinishTask:
    """Tests for finish_task tool."""

    def test_complete_task(self, temp_storage):
        # Setup: task_a -> task_b
        add_node.add_node(temp_storage, {"node_id": "task_a"})
        add_node.add_node(temp_storage, {
            "node_id": "task_b",
            "dependencies": ["task_a"],
            "expectations": [make_contract("task_a")],
        })

        # Get and complete task_a
        get_task.get_task(temp_storage, {"agent_id": "agent_1", "task_id": "task_a"})
        result = finish_task.finish_task(temp_storage, {
            "task_id": "task_a",
            "success": True,
            "result": "Task completed successfully",
        })

        assert result["success"] is True

        # Verify state
        with temp_storage.lock():
            cascade = temp_storage.load()
            assert cascade.nodes["task_a"].state == NodeState.COMPLETED
            # Dependent should be unblocked
            assert cascade.nodes["task_b"].in_degree == 0
            assert cascade.nodes["task_b"].state == NodeState.READY

    def test_fail_task(self, temp_storage):
        add_node.add_node(temp_storage, {"node_id": "task_a"})
        get_task.get_task(temp_storage, {"agent_id": "agent_1", "task_id": "task_a"})

        result = finish_task.finish_task(temp_storage, {
            "task_id": "task_a",
            "success": False,
            "result": "Something went wrong",
        })

        assert result["success"] is True

        with temp_storage.lock():
            cascade = temp_storage.load()
            assert cascade.nodes["task_a"].state == NodeState.FAILED

    def test_fail_task_cascade(self, temp_storage):
        # Setup: task_a -> task_b, task_a -> task_c
        add_node.add_node(temp_storage, {"node_id": "task_a"})
        add_node.add_node(temp_storage, {
            "node_id": "task_b",
            "dependencies": ["task_a"],
            "expectations": [make_contract("task_a")],
        })
        add_node.add_node(temp_storage, {
            "node_id": "task_c",
            "dependencies": ["task_a"],
            "expectations": [make_contract("task_a")],
        })

        get_task.get_task(temp_storage, {"agent_id": "agent_1", "task_id": "task_a"})
        result = finish_task.finish_task(temp_storage, {
            "task_id": "task_a",
            "success": False,
            "cascade": True,
        })

        assert result["success"] is True

        with temp_storage.lock():
            cascade = temp_storage.load()
            assert cascade.nodes["task_a"].state == NodeState.FAILED
            assert cascade.nodes["task_b"].state == NodeState.FAILED
            assert cascade.nodes["task_c"].state == NodeState.FAILED

    def test_release_task(self, temp_storage):
        add_node.add_node(temp_storage, {"node_id": "task_a"})

        # Get task first
        get_task.get_task(temp_storage, {"agent_id": "agent_1", "task_id": "task_a"})

        with temp_storage.lock():
            cascade = temp_storage.load()
            assert cascade.nodes["task_a"].state == NodeState.ACTIVE

        # Release it
        result = finish_task.finish_task(temp_storage, {
            "task_id": "task_a",
            "release": True,
            "result": "Need more information",
        })

        assert result["success"] is True

        with temp_storage.lock():
            cascade = temp_storage.load()
            assert cascade.nodes["task_a"].state == NodeState.READY

        # Task should be available again
        result2 = get_task.get_task(temp_storage, {"task_id": "task_a", "agent_id": "agent_2"})
        assert result2["success"] is True


class TestAddNode:
    """Tests for add_node tool."""

    def test_add_basic_node(self, temp_storage):
        result = add_node.add_node(temp_storage, {
            "node_id": "new_task",
        })
        assert result["success"] is True

        with temp_storage.lock():
            cascade = temp_storage.load()
            assert "new_task" in cascade.nodes
            # No dependencies -> READY
            assert cascade.nodes["new_task"].state == NodeState.READY

    def test_add_node_with_dependencies(self, temp_storage):
        # Create a proper chain: root -> task_a, root -> task_b, then new_task depends on both
        add_node.add_node(temp_storage, {"node_id": "root"})
        add_node.add_node(temp_storage, {
            "node_id": "task_a",
            "dependencies": ["root"],
            "expectations": [make_contract("root")],
        })
        add_node.add_node(temp_storage, {
            "node_id": "task_b",
            "dependencies": ["root"],
            "expectations": [make_contract("root")],
        })

        result = add_node.add_node(temp_storage, {
            "node_id": "new_task",
            "dependencies": ["task_a", "task_b"],
            "expectations": [make_contract("task_a"), make_contract("task_b")],
        })
        assert result["success"] is True

        with temp_storage.lock():
            cascade = temp_storage.load()
            assert cascade.nodes["new_task"].in_degree == 2
            # Has dependencies -> PENDING
            assert cascade.nodes["new_task"].state == NodeState.PENDING

    def test_add_node_dependency_not_exists(self, temp_storage):
        # First add a root node so the graph is non-empty
        add_node.add_node(temp_storage, {"node_id": "root"})

        result = add_node.add_node(temp_storage, {
            "node_id": "new_task",
            "dependencies": ["non_existent"],
            "expectations": [make_contract("non_existent")],
        })
        assert result["success"] is False
        assert "not found" in result["message"]

    def test_reject_isolated_node_in_non_empty_graph(self, temp_storage):
        # First node can be added without dependencies (root node)
        result = add_node.add_node(temp_storage, {
            "node_id": "root",
        })
        assert result["success"] is True

        # Second node without dependencies should be rejected
        result = add_node.add_node(temp_storage, {
            "node_id": "isolated",
        })
        assert result["success"] is False
        assert "Isolated nodes not allowed" in result["message"]

        # Node with dependencies should be allowed
        result = add_node.add_node(temp_storage, {
            "node_id": "child",
            "dependencies": ["root"],
            "expectations": [make_contract("root")],
        })
        assert result["success"] is True

    def test_add_node_with_dependents(self, temp_storage):
        # Add root and child
        add_node.add_node(temp_storage, {"node_id": "root"})
        add_node.add_node(temp_storage, {
            "node_id": "child",
            "dependencies": ["root"],
            "expectations": [make_contract("root")],
        })

        # Add a new node that will be a dependency of existing node
        result = add_node.add_node(temp_storage, {
            "node_id": "new_parent",
            "dependents": ["child"],
            "expectations": [make_contract("child", "Child expects input", "New parent provides input")],
        })
        assert result["success"] is True

        with temp_storage.lock():
            cascade = temp_storage.load()
            # child should now have 2 dependencies
            assert cascade.nodes["child"].in_degree == 2

    def test_reject_disconnected_subgraph(self, temp_storage):
        """Test that adding a node that creates a disconnected subgraph is rejected."""
        # Create a connected graph: root -> child
        add_node.add_node(temp_storage, {"node_id": "root"})
        add_node.add_node(temp_storage, {
            "node_id": "child",
            "dependencies": ["root"],
            "expectations": [make_contract("root")],
        })

        # Try to add two nodes that form their own disconnected subgraph
        # First add disconnected_root (should fail - it's isolated from existing graph)
        result = add_node.add_node(temp_storage, {
            "node_id": "disconnected_root",
        })
        assert result["success"] is False
        assert "Isolated nodes not allowed" in result["message"]

    def test_missing_contract_for_dependency(self, temp_storage):
        """Test that adding node without contract for dependency fails."""
        add_node.add_node(temp_storage, {"node_id": "root"})

        result = add_node.add_node(temp_storage, {
            "node_id": "child",
            "dependencies": ["root"],
            # Missing expectations
        })
        assert result["success"] is False
        assert "Missing contract" in result["message"]

    def test_empty_expectation_rejected(self, temp_storage):
        """Test that empty expectation is rejected."""
        add_node.add_node(temp_storage, {"node_id": "root"})

        result = add_node.add_node(temp_storage, {
            "node_id": "child",
            "dependencies": ["root"],
            "expectations": [{"node_id": "root", "expectation": "", "promise": "some promise"}],
        })
        assert result["success"] is False
        assert "expectation is required" in result["message"]

    def test_empty_promise_rejected(self, temp_storage):
        """Test that empty promise is rejected."""
        add_node.add_node(temp_storage, {"node_id": "root"})

        result = add_node.add_node(temp_storage, {
            "node_id": "child",
            "dependencies": ["root"],
            "expectations": [{"node_id": "root", "expectation": "some expectation", "promise": ""}],
        })
        assert result["success"] is False
        assert "promise is required" in result["message"]


class TestRefineNode:
    """Tests for refine_node tool."""

    def test_refine_node(self, temp_storage):
        # Create proper chain: root -> task_a, root -> task_b
        add_node.add_node(temp_storage, {"node_id": "root"})
        add_node.add_node(temp_storage, {
            "node_id": "task_a",
            "dependencies": ["root"],
            "expectations": [make_contract("root")],
        })
        add_node.add_node(temp_storage, {
            "node_id": "task_b",
            "dependencies": ["root"],
            "expectations": [make_contract("root")],
        })

        # Now add dependency: task_b -> task_a
        result = refine_node.refine_node(temp_storage, {
            "node_id": "task_b",
            "dependency_id": "task_a",
            "expectation": "Expect output from task_a",
            "promise": "Promise to provide results",
        })

        assert result["success"] is True

        with temp_storage.lock():
            cascade = temp_storage.load()
            # task_b now has two dependencies: root and task_a
            assert cascade.nodes["task_b"].in_degree == 2

    def test_refine_node_requires_contract(self, temp_storage):
        """Test that refine_node requires expectation and promise."""
        add_node.add_node(temp_storage, {"node_id": "root"})
        add_node.add_node(temp_storage, {
            "node_id": "task_a",
            "dependencies": ["root"],
            "expectations": [make_contract("root")],
        })

        # Missing expectation
        result = refine_node.refine_node(temp_storage, {
            "node_id": "task_a",
            "dependency_id": "root",
            "promise": "some promise",
        })
        assert result["success"] is False
        assert "expectation" in result["message"].lower()

        # Missing promise
        result = refine_node.refine_node(temp_storage, {
            "node_id": "task_a",
            "dependency_id": "root",
            "expectation": "some expectation",
        })
        assert result["success"] is False
        assert "promise" in result["message"].lower()


class TestRemoveNode:
    """Tests for remove_node tool."""

    def test_remove_node(self, temp_storage):
        # Create proper chain: root -> task_a -> task_b
        add_node.add_node(temp_storage, {"node_id": "root"})
        add_node.add_node(temp_storage, {
            "node_id": "task_a",
            "dependencies": ["root"],
            "expectations": [make_contract("root")],
        })
        add_node.add_node(temp_storage, {
            "node_id": "task_b",
            "dependencies": ["task_a"],
            "expectations": [make_contract("task_a")],
        })

        result = remove_node.remove_node(temp_storage, {"node_id": "task_b"})
        assert result["success"] is True

        with temp_storage.lock():
            cascade = temp_storage.load()
            assert "task_b" not in cascade.nodes


class TestSplitNode:
    """Tests for split_node tool."""

    def test_split_node(self, temp_storage):
        add_node.add_node(temp_storage, {"node_id": "task_a"})
        add_node.add_node(temp_storage, {
            "node_id": "task_b",
            "dependencies": ["task_a"],
            "expectations": [make_contract("task_a")],
        })

        result = split_node.split_node(temp_storage, {
            "parent_id": "task_b",
            "new_nodes": [
                {"node_id": "task_b1"},
                {"node_id": "task_b2"},
            ],
        })
        assert result["success"] is True

        with temp_storage.lock():
            cascade = temp_storage.load()
            assert "task_b" not in cascade.nodes
            assert "task_b1" in cascade.nodes


class TestListNodes:
    """Tests for list_nodes tool."""

    def test_list_all_nodes(self, temp_storage):
        # Create proper chain: root -> task_a, root -> task_b, root -> task_c
        add_node.add_node(temp_storage, {"node_id": "root"})
        add_node.add_node(temp_storage, {
            "node_id": "task_a",
            "dependencies": ["root"],
            "expectations": [make_contract("root")],
        })
        add_node.add_node(temp_storage, {
            "node_id": "task_b",
            "dependencies": ["root"],
            "expectations": [make_contract("root")],
        })
        add_node.add_node(temp_storage, {
            "node_id": "task_c",
            "dependencies": ["root"],
            "expectations": [make_contract("root")],
        })

        result = list_nodes.list_nodes(temp_storage, {})
        assert result["success"] is True
        assert result["data"]["count"] == 4  # root + 3 children

    def test_list_nodes_with_filter(self, temp_storage):
        add_node.add_node(temp_storage, {"node_id": "task_a"})
        add_node.add_node(temp_storage, {
            "node_id": "task_b",
            "dependencies": ["task_a"],
            "expectations": [make_contract("task_a")],
        })

        result = list_nodes.list_nodes(temp_storage, {"state_filter": "READY"})
        assert result["success"] is True
        assert result["data"]["count"] == 1


class TestExecuteTool:
    """Tests for the execute_tool wrapper function."""

    def test_execute_valid_tool(self, temp_storage):
        result = execute_tool(temp_storage, "add_node", {
            "node_id": "test",
        })
        assert result["success"] is True

    def test_execute_invalid_tool(self, temp_storage):
        with pytest.raises(ValueError, match="Unknown tool"):
            execute_tool(temp_storage, "invalid_tool", {})
