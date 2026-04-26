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

from cascade.client import CascadeClient, Contract
from cascade.core.state import NodeState
from cascade.view import get_node_view


class TestSplitDuringExecution:
    """Split a node while the graph is being executed."""

    def test_split_pending_node_while_upstream_active(self, client: CascadeClient, temp_storage):
        """Split a PENDING task while its upstream dependency is being worked on."""
        # Build: a -> b -> c
        client.add("a")
        client.add(
            "b",
            deps={"a": Contract("Expect output from a", "Promise output to dependent")},
        )
        client.add(
            "c",
            deps={"b": Contract("Expect output from b", "Promise output to dependent")},
        )

        # Agent claims a (a is ACTIVE, b and c are PENDING)
        client.claim("agent-1")

        # Meanwhile, someone decides b is too broad -> split into b1, b2
        result = client.split("b", into=["b1", "b2"])
        assert result.success, result.message

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

    def test_split_then_complete_upstream(self, client: CascadeClient, temp_storage):
        """After splitting, completing the upstream should unblock split nodes."""
        client.add("a")
        client.add(
            "b",
            deps={"a": Contract("Expect output from a", "Promise output to dependent")},
        )

        # Split b before a completes
        client.split("b", into=["b1", "b2"])

        # Now complete a
        client.claim("agent-1", "a")
        client.complete(
            "a",
            summary="Analysis complete",
            critical={"result": "data from a"},
        )

        # b1 and b2 should now be READY
        with temp_storage.lock():
            cascade = temp_storage.load()
            assert cascade.nodes["b1"].state == NodeState.READY
            assert cascade.nodes["b2"].state == NodeState.READY

    def test_split_context_propagation(self, client: CascadeClient, temp_storage):
        """Context from completed upstream should reach split nodes."""
        client.add("a")
        client.add(
            "b",
            deps={"a": Contract("Expect output from a", "Promise output to dependent")},
        )

        # Complete a with context
        client.claim("agent-1", "a")
        client.complete(
            "a",
            summary="Found 3 bugs",
            critical={"bug_count": 3, "severity": "high"},
        )

        # Split b into b1, b2
        client.split("b", into=["b1", "b2"])

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

    def test_refine_ready_node_becomes_pending(self, client: CascadeClient, temp_storage):
        """A READY task gets a new dependency -> goes back to PENDING."""
        client.add("a")
        client.add("b")

        # Both are READY. Now add dependency: b depends on a.
        result = client.refine(
            "b",
            "a",
            expectation="Need a's output first",
            promise="Will provide output",
        )
        assert result.success

        with temp_storage.lock():
            cascade = temp_storage.load()
            # b should now be PENDING (a is not completed)
            assert cascade.nodes["b"].state == NodeState.PENDING
            assert cascade.pending_dependency_count("b") == 1

    def test_refine_while_agent_active_on_another(self, client: CascadeClient, temp_storage):
        """Add a dependency while an agent is working on a different task."""
        client.add("a")
        client.add("b")
        client.add("c")

        # Agent starts working on a
        client.claim("agent-1", "a")

        # Meanwhile, someone refines: c now depends on b
        client.refine(
            "c",
            "b",
            expectation="Need b's output",
            promise="Will provide output",
        )

        with temp_storage.lock():
            cascade = temp_storage.load()
            assert cascade.nodes["a"].state == NodeState.ACTIVE
            assert cascade.nodes["c"].state == NodeState.PENDING
            assert cascade.has_dependency("c", "b")

    def test_refine_then_complete_chain(self, client: CascadeClient):
        """After refining, completing the chain unblocks correctly."""
        client.add("a")
        client.add("b")

        # Refine: b depends on a
        client.refine("b", "a", expectation="E", promise="P")

        # Complete a
        client.claim("a1", "a")
        client.complete("a", summary="Done", critical={"from_a": True})

        # b should be READY and see a's context
        task = client.claim("a2", "b")
        assert task.upstream[0]["delivered"]["critical"]["from_a"] is True


class TestAddNodeDuringExecution:
    """Add new nodes to a running graph."""

    def test_add_node_to_running_graph(self, client: CascadeClient, temp_storage):
        """Add a new task while others are being executed."""
        client.add("a")
        client.add(
            "b",
            deps={"a": Contract("Expect output from a", "Promise output to dependent")},
        )

        # Agent starts a
        client.claim("agent-1", "a")

        # Someone adds a new independent task
        result = client.add("c_independent")
        assert result.success

        # And a new task depending on the running task
        result = client.add(
            "d_depends_on_a",
            deps={"a": Contract("Expect output from a", "Promise output to dependent")},
        )
        assert result.success

        with temp_storage.lock():
            cascade = temp_storage.load()
            # c is READY (independent)
            assert cascade.nodes["c_independent"].state == NodeState.READY
            # d is PENDING (depends on active a)
            assert cascade.nodes["d_depends_on_a"].state == NodeState.PENDING

    def test_add_node_depending_on_completed(self, client: CascadeClient):
        """Add a node that depends on an already-completed task -> immediately READY."""
        client.add("a")
        client.claim("a1", "a")
        client.complete("a", summary="Done", critical={"x": 1})

        # Add new node depending on completed a
        result = client.add(
            "late_joiner",
            deps={"a": Contract("Expect output from a", "Promise output to dependent")},
        )
        assert result.success

        # Should be immediately READY and see a's context
        task = client.claim("a2", "late_joiner")
        assert task.upstream[0]["delivered"]["critical"]["x"] == 1


class TestRemoveDuringExecution:
    """Remove nodes from a running graph."""

    def test_remove_pending_node(self, client: CascadeClient, temp_storage):
        """Remove a PENDING task -- its dependents should adjust."""
        client.add("a")
        client.add(
            "b",
            deps={"a": Contract("Expect output from a", "Promise output to dependent")},
        )
        client.add(
            "c",
            deps={"b": Contract("Expect output from b", "Promise output to dependent")},
        )

        # Remove b -- c loses its dependency
        result = client.remove("b")
        assert result.success

        with temp_storage.lock():
            cascade = temp_storage.load()
            assert "b" not in cascade.nodes
            # c should now have no dependencies -> READY
            assert cascade.pending_dependency_count("c") == 0
            assert cascade.nodes["c"].state == NodeState.READY


class TestCombinedDynamicEditing:
    """Complex scenarios combining multiple dynamic edits."""

    def test_full_dynamic_workflow(self, client: CascadeClient, temp_storage):
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
        client.add("analyze")
        client.add(
            "implement",
            deps={"analyze": Contract("Expect output from analyze", "Promise output to dependent")},
        )
        client.add(
            "test",
            deps={
                "implement": Contract("Expect output from implement", "Promise output to dependent")
            },
        )

        # 2. Agent starts analyze
        client.claim("a1", "analyze")

        # 3. Split implement while analyze is running
        client.split("implement", into=["impl_auth", "impl_api"])

        # 4. Complete analyze with context
        client.complete(
            "analyze",
            summary="Found auth and API requirements",
            critical={"needs_auth": True, "api_version": "v2"},
        )

        # 5. Both impl nodes should be READY
        with temp_storage.lock():
            cascade = temp_storage.load()
            assert cascade.nodes["impl_auth"].state == NodeState.READY
            assert cascade.nodes["impl_api"].state == NodeState.READY

        # Agents pick them up
        client.claim("a2", "impl_auth")
        client.claim("a3", "impl_api")

        # 6. impl_api agent discovers it needs a schema task first
        client.add(
            "design_schema",
            dependents={
                "impl_api": Contract("API schema design", "Schema for v2 API"),
            },
        )

        # impl_api should still be ACTIVE (refine only affects PENDING/READY)
        with temp_storage.lock():
            cascade = temp_storage.load()
            assert cascade.nodes["impl_api"].state == NodeState.ACTIVE

        # 7. Complete everything
        client.complete("impl_auth", summary="Auth module done")

        # design_schema is READY (no deps)
        client.claim("a4", "design_schema")
        client.complete("design_schema", summary="Schema designed")

        client.complete("impl_api", summary="API module done")

        # test should now be READY (all deps completed)
        with temp_storage.lock():
            cascade = temp_storage.load()
            assert cascade.nodes["test"].state == NodeState.READY

        # Complete test
        client.claim("a5", "test")
        client.complete("test", summary="All tests pass")

        # Everything should be COMPLETED
        with temp_storage.lock():
            cascade = temp_storage.load()
            for nid, node in cascade.nodes.items():
                assert node.state == NodeState.COMPLETED, f"{nid} is {node.state}"
