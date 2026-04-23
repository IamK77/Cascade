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

"""Tests for dynamic graph editing during execution.

Cascade allows the graph to mutate while agents are working.
These tests verify that the system remains consistent when
nodes are split, refined, added, or removed mid-execution.
"""

from cascade.core.state import NodeState
from cascade.view import get_node_view
from tools import add_node, finish_task, get_task, refine_node, remove_node, split_node


def make_contract(node_id: str, expectation: str = "", promise: str = "") -> dict:
    return {
        "node_id": node_id,
        "expectation": expectation or f"Expect output from {node_id}",
        "promise": promise or "Promise output to dependent",
    }


class TestSplitDuringExecution:
    """Split a node while the graph is being executed."""

    def test_split_pending_node_while_upstream_active(self, temp_storage):
        """Split a PENDING task while its upstream dependency is being worked on."""
        # Build: a -> b -> c
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

        # Agent claims a (a is ACTIVE, b and c are PENDING)
        get_task.get_task(temp_storage, {"agent_id": "agent-1"})

        # Meanwhile, someone decides b is too broad → split into b1, b2
        result = split_node.split_node(temp_storage, {
            "parent_id": "b",
            "new_nodes": [{"node_id": "b1"}, {"node_id": "b2"}],
        })
        assert result["success"], result["message"]

        with temp_storage.lock():
            cascade = temp_storage.load()
            # b should be gone, b1 and b2 should exist
            assert "b" not in cascade.nodes
            assert "b1" in cascade.nodes
            assert "b2" in cascade.nodes

            # b1 and b2 should depend on a (inherited)
            assert cascade.has_dependency("b1", "a")
            assert cascade.has_dependency("b2", "a")

            # c should now depend on b1 and b2 (rewired from b)
            assert cascade.has_dependency("c", "b1")
            assert cascade.has_dependency("c", "b2")

            # a is still ACTIVE
            assert cascade.nodes["a"].state == NodeState.ACTIVE

    def test_split_then_complete_upstream(self, temp_storage):
        """After splitting, completing the upstream should unblock split nodes."""
        add_node.add_node(temp_storage, {"node_id": "a"})
        add_node.add_node(temp_storage, {
            "node_id": "b",
            "dependencies": ["a"],
            "expectations": [make_contract("a")],
        })

        # Split b before a completes
        split_node.split_node(temp_storage, {
            "parent_id": "b",
            "new_nodes": [{"node_id": "b1"}, {"node_id": "b2"}],
        })

        # Now complete a
        get_task.get_task(temp_storage, {"agent_id": "agent-1", "task_id": "a"})
        finish_task.finish_task(temp_storage, {
            "task_id": "a",
            "success": True,
            "summary": "Analysis complete",
            "critical": {"result": "data from a"},
        })

        # b1 and b2 should now be READY
        with temp_storage.lock():
            cascade = temp_storage.load()
            assert cascade.nodes["b1"].state == NodeState.READY
            assert cascade.nodes["b2"].state == NodeState.READY

    def test_split_context_propagation(self, temp_storage):
        """Context from completed upstream should reach split nodes."""
        add_node.add_node(temp_storage, {"node_id": "a"})
        add_node.add_node(temp_storage, {
            "node_id": "b",
            "dependencies": ["a"],
            "expectations": [make_contract("a")],
        })

        # Complete a with context
        get_task.get_task(temp_storage, {"agent_id": "agent-1", "task_id": "a"})
        finish_task.finish_task(temp_storage, {
            "task_id": "a",
            "success": True,
            "summary": "Found 3 bugs",
            "critical": {"bug_count": 3, "severity": "high"},
        })

        # Split b into b1, b2
        split_node.split_node(temp_storage, {
            "parent_id": "b",
            "new_nodes": [{"node_id": "b1"}, {"node_id": "b2"}],
        })

        # b1 should see a's context
        with temp_storage.lock():
            cascade = temp_storage.load()
            view = get_node_view(cascade, "b1")
            assert "upstream" in view
            up = view["upstream"]
            assert up[0]["node_id"] == "a"
            assert up[0]["delivered"]["critical"]["bug_count"] == 3
            assert up[0]["delivered"]["summary"] == "Found 3 bugs"


class TestRefineDuringExecution:
    """Add new dependencies to nodes mid-execution."""

    def test_refine_ready_node_becomes_pending(self, temp_storage):
        """A READY task gets a new dependency → goes back to PENDING."""
        add_node.add_node(temp_storage, {"node_id": "a"})
        add_node.add_node(temp_storage, {"node_id": "b"})

        # Both are READY. Now add dependency: b depends on a.
        result = refine_node.refine_node(temp_storage, {
            "node_id": "b",
            "dependency_id": "a",
            "expectation": "Need a's output first",
            "promise": "Will provide output",
        })
        assert result["success"]

        with temp_storage.lock():
            cascade = temp_storage.load()
            # b should now be PENDING (a is not completed)
            assert cascade.nodes["b"].state == NodeState.PENDING
            assert cascade.pending_dependency_count("b") == 1

    def test_refine_while_agent_active_on_another(self, temp_storage):
        """Add a dependency while an agent is working on a different task."""
        add_node.add_node(temp_storage, {"node_id": "a"})
        add_node.add_node(temp_storage, {"node_id": "b"})
        add_node.add_node(temp_storage, {"node_id": "c"})

        # Agent starts working on a
        get_task.get_task(temp_storage, {"agent_id": "agent-1", "task_id": "a"})

        # Meanwhile, someone refines: c now depends on b
        refine_node.refine_node(temp_storage, {
            "node_id": "c",
            "dependency_id": "b",
            "expectation": "Need b's output",
            "promise": "Will provide output",
        })

        with temp_storage.lock():
            cascade = temp_storage.load()
            assert cascade.nodes["a"].state == NodeState.ACTIVE
            assert cascade.nodes["c"].state == NodeState.PENDING
            assert cascade.has_dependency("c", "b")

    def test_refine_then_complete_chain(self, temp_storage):
        """After refining, completing the chain unblocks correctly."""
        add_node.add_node(temp_storage, {"node_id": "a"})
        add_node.add_node(temp_storage, {"node_id": "b"})

        # Refine: b depends on a
        refine_node.refine_node(temp_storage, {
            "node_id": "b",
            "dependency_id": "a",
            "expectation": "E",
            "promise": "P",
        })

        # Complete a
        get_task.get_task(temp_storage, {"agent_id": "a1", "task_id": "a"})
        finish_task.finish_task(temp_storage, {
            "task_id": "a",
            "success": True,
            "summary": "Done",
            "critical": {"from_a": True},
        })

        # b should be READY and see a's context
        result = get_task.get_task(temp_storage, {"agent_id": "a2", "task_id": "b"})
        assert result["success"]
        assert result["data"]["task_info"]["upstream"][0]["delivered"]["critical"]["from_a"] is True


class TestAddNodeDuringExecution:
    """Add new nodes to a running graph."""

    def test_add_node_to_running_graph(self, temp_storage):
        """Add a new task while others are being executed."""
        add_node.add_node(temp_storage, {"node_id": "a"})
        add_node.add_node(temp_storage, {
            "node_id": "b",
            "dependencies": ["a"],
            "expectations": [make_contract("a")],
        })

        # Agent starts a
        get_task.get_task(temp_storage, {"agent_id": "agent-1", "task_id": "a"})

        # Someone adds a new independent task
        result = add_node.add_node(temp_storage, {"node_id": "c_independent"})
        assert result["success"]

        # And a new task depending on the running task
        result = add_node.add_node(temp_storage, {
            "node_id": "d_depends_on_a",
            "dependencies": ["a"],
            "expectations": [make_contract("a")],
        })
        assert result["success"]

        with temp_storage.lock():
            cascade = temp_storage.load()
            # c is READY (independent)
            assert cascade.nodes["c_independent"].state == NodeState.READY
            # d is PENDING (depends on active a)
            assert cascade.nodes["d_depends_on_a"].state == NodeState.PENDING

    def test_add_node_depending_on_completed(self, temp_storage):
        """Add a node that depends on an already-completed task → immediately READY."""
        add_node.add_node(temp_storage, {"node_id": "a"})
        get_task.get_task(temp_storage, {"agent_id": "a1", "task_id": "a"})
        finish_task.finish_task(temp_storage, {
            "task_id": "a", "success": True,
            "summary": "Done", "critical": {"x": 1},
        })

        # Add new node depending on completed a
        result = add_node.add_node(temp_storage, {
            "node_id": "late_joiner",
            "dependencies": ["a"],
            "expectations": [make_contract("a")],
        })
        assert result["success"]

        # Should be immediately READY and see a's context
        result = get_task.get_task(temp_storage, {"agent_id": "a2", "task_id": "late_joiner"})
        assert result["success"]
        assert result["data"]["task_info"]["upstream"][0]["delivered"]["critical"]["x"] == 1


class TestRemoveDuringExecution:
    """Remove nodes from a running graph."""

    def test_remove_pending_node(self, temp_storage):
        """Remove a PENDING task — its dependents should adjust."""
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

        # Remove b — c loses its dependency
        result = remove_node.remove_node(temp_storage, {"node_id": "b"})
        assert result["success"]

        with temp_storage.lock():
            cascade = temp_storage.load()
            assert "b" not in cascade.nodes
            # c should now have no dependencies → READY
            assert cascade.pending_dependency_count("c") == 0
            assert cascade.nodes["c"].state == NodeState.READY


class TestCombinedDynamicEditing:
    """Complex scenarios combining multiple dynamic edits."""

    def test_full_dynamic_workflow(self, temp_storage):
        """
        Simulate a realistic dynamic workflow:
        1. Build initial graph: analyze -> implement -> test
        2. Agent starts analyze
        3. While analyze runs, split implement into impl_auth + impl_api
        4. Complete analyze
        5. Agents pick up impl_auth and impl_api in parallel
        6. impl_api agent discovers missing dependency, refines
        7. Complete everything
        """
        # 1. Initial graph
        add_node.add_node(temp_storage, {"node_id": "analyze"})
        add_node.add_node(temp_storage, {
            "node_id": "implement",
            "dependencies": ["analyze"],
            "expectations": [make_contract("analyze")],
        })
        add_node.add_node(temp_storage, {
            "node_id": "test",
            "dependencies": ["implement"],
            "expectations": [make_contract("implement")],
        })

        # 2. Agent starts analyze
        get_task.get_task(temp_storage, {"agent_id": "a1", "task_id": "analyze"})

        # 3. Split implement while analyze is running
        split_node.split_node(temp_storage, {
            "parent_id": "implement",
            "new_nodes": [{"node_id": "impl_auth"}, {"node_id": "impl_api"}],
        })

        # 4. Complete analyze with context
        finish_task.finish_task(temp_storage, {
            "task_id": "analyze",
            "success": True,
            "summary": "Found auth and API requirements",
            "critical": {"needs_auth": True, "api_version": "v2"},
        })

        # 5. Both impl nodes should be READY
        with temp_storage.lock():
            cascade = temp_storage.load()
            assert cascade.nodes["impl_auth"].state == NodeState.READY
            assert cascade.nodes["impl_api"].state == NodeState.READY

        # Agents pick them up
        get_task.get_task(temp_storage, {"agent_id": "a2", "task_id": "impl_auth"})
        get_task.get_task(temp_storage, {"agent_id": "a3", "task_id": "impl_api"})

        # 6. impl_api agent discovers it needs a schema task first
        add_node.add_node(temp_storage, {
            "node_id": "design_schema",
            "dependents": ["impl_api"],
            "expectations": [make_contract("impl_api", "API schema design", "Schema for v2 API")],
        })

        # impl_api should still be ACTIVE (refine only affects PENDING/READY)
        with temp_storage.lock():
            cascade = temp_storage.load()
            assert cascade.nodes["impl_api"].state == NodeState.ACTIVE

        # 7. Complete everything
        finish_task.finish_task(temp_storage, {
            "task_id": "impl_auth",
            "success": True,
            "summary": "Auth module done",
        })

        # design_schema is READY (no deps)
        get_task.get_task(temp_storage, {"agent_id": "a4", "task_id": "design_schema"})
        finish_task.finish_task(temp_storage, {
            "task_id": "design_schema",
            "success": True,
            "summary": "Schema designed",
        })

        finish_task.finish_task(temp_storage, {
            "task_id": "impl_api",
            "success": True,
            "summary": "API module done",
        })

        # test should now be READY (all deps completed)
        with temp_storage.lock():
            cascade = temp_storage.load()
            assert cascade.nodes["test"].state == NodeState.READY

        # Complete test
        get_task.get_task(temp_storage, {"agent_id": "a5", "task_id": "test"})
        finish_task.finish_task(temp_storage, {
            "task_id": "test",
            "success": True,
            "summary": "All tests pass",
        })

        # Everything should be COMPLETED
        with temp_storage.lock():
            cascade = temp_storage.load()
            for nid, node in cascade.nodes.items():
                assert node.state == NodeState.COMPLETED, f"{nid} is {node.state}"
