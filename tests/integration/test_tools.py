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

"""Tests for Cascade operations via CascadeClient."""

import time

from cascade.client import CascadeClient, Contract
from cascade.core.state import NodeState


class TestGetTask:
    """Tests for claim (formerly get_task)."""

    def test_get_any_task(self, client: CascadeClient):
        client.add("task_a")
        client.add(
            "task_b",
            deps={"task_a": Contract("Expect output from task_a", "Promise output to dependent")},
        )

        r = client.claim("agent_1")
        assert r.success
        assert r.data["state"] == "ACTIVE"
        assert r.data["task_id"] == "task_a"

    def test_get_specific_task(self, client: CascadeClient, temp_storage):
        client.add("task_a")
        r = client.claim("agent_1", "task_a")
        assert r.data["task_id"] == "task_a"

        with temp_storage.lock():
            cascade = temp_storage.load()
            assert cascade.nodes["task_a"].state == NodeState.ACTIVE

    def test_get_task_not_ready(self, client: CascadeClient):
        client.add("task_a")
        client.add(
            "task_b",
            deps={"task_a": Contract("Expect output from task_a", "Promise output to dependent")},
        )
        result = client.claim("agent_1", "task_b")
        assert result.success is False

    def test_agent_tracking(self, client: CascadeClient):
        client.add("root")
        client.add(
            "task_a",
            deps={"root": Contract("Expect output from root", "Promise output to dependent")},
        )
        client.add(
            "task_b",
            deps={"root": Contract("Expect output from root", "Promise output to dependent")},
        )

        result = client.claim("agent_1")
        assert result.data["task_id"] == "root"

        # Second claim fails with ALREADY_HAS_ACTIVE — agent must finish first
        result = client.claim("agent_1")
        assert result.success is False
        assert result.code == "ALREADY_HAS_ACTIVE"
        assert result.data.get("current_task") == "root"

    def test_no_available_tasks(self, client: CascadeClient):
        client.add("task_a")
        client.claim("agent_1")
        client.complete("task_a")

        result = client.claim("agent_2")
        assert result.success is False

    def test_agent_id_required(self, client: CascadeClient):
        client.add("task_a")
        result = client.claim("")
        assert result.success is False
        assert "agent_id is required" in result.message


class TestFinishTask:
    """Tests for complete/fail/release (formerly finish_task)."""

    def test_complete_task(self, client: CascadeClient, temp_storage):
        client.add("task_a")
        client.add(
            "task_b",
            deps={"task_a": Contract("Expect output from task_a", "Promise output to dependent")},
        )

        client.claim("agent_1", "task_a")
        result = client.complete("task_a", summary="Task completed successfully")
        assert result.success is True

        with temp_storage.lock():
            cascade = temp_storage.load()
            assert cascade.nodes["task_a"].state == NodeState.COMPLETED
            assert cascade.pending_dependency_count("task_b") == 0
            assert cascade.nodes["task_b"].state == NodeState.READY

    def test_fail_task(self, client: CascadeClient, temp_storage):
        client.add("task_a")
        client.claim("agent_1", "task_a")

        result = client.fail("task_a", reason="Something went wrong")
        assert result.success is True

        with temp_storage.lock():
            cascade = temp_storage.load()
            assert cascade.nodes["task_a"].state == NodeState.FAILED

    def test_fail_task_cascade(self, client: CascadeClient, temp_storage):
        client.add("task_a")
        client.add(
            "task_b",
            deps={"task_a": Contract("Expect output from task_a", "Promise output to dependent")},
        )
        client.add(
            "task_c",
            deps={"task_a": Contract("Expect output from task_a", "Promise output to dependent")},
        )

        client.claim("agent_1", "task_a")
        result = client.fail("task_a", cascade=True)
        assert result.success is True

        with temp_storage.lock():
            cascade = temp_storage.load()
            assert cascade.nodes["task_a"].state == NodeState.FAILED
            assert cascade.nodes["task_b"].state == NodeState.FAILED
            assert cascade.nodes["task_c"].state == NodeState.FAILED

    def test_release_task(self, client: CascadeClient, temp_storage):
        client.add("task_a")
        client.claim("agent_1", "task_a")

        with temp_storage.lock():
            cascade = temp_storage.load()
            assert cascade.nodes["task_a"].state == NodeState.ACTIVE

        result = client.release("task_a", reason="Need more information")
        assert result.success is True

        with temp_storage.lock():
            cascade = temp_storage.load()
            assert cascade.nodes["task_a"].state == NodeState.READY

        r2 = client.claim("agent_2", "task_a")
        assert r2.data["task_id"] == "task_a"


class TestAddNode:
    """Tests for add (formerly add_node)."""

    def test_add_basic_node(self, client: CascadeClient, temp_storage):
        result = client.add("new_task")
        assert result.success is True

        with temp_storage.lock():
            cascade = temp_storage.load()
            assert "new_task" in cascade.nodes
            assert cascade.nodes["new_task"].state == NodeState.READY

    def test_add_node_with_dependencies(self, client: CascadeClient, temp_storage):
        client.add("root")
        client.add(
            "task_a",
            deps={"root": Contract("Expect output from root", "Promise output to dependent")},
        )
        client.add(
            "task_b",
            deps={"root": Contract("Expect output from root", "Promise output to dependent")},
        )

        result = client.add(
            "new_task",
            deps={
                "task_a": Contract("Expect output from task_a", "Promise output to dependent"),
                "task_b": Contract("Expect output from task_b", "Promise output to dependent"),
            },
        )
        assert result.success is True

        with temp_storage.lock():
            cascade = temp_storage.load()
            assert cascade.pending_dependency_count("new_task") == 2
            assert cascade.nodes["new_task"].state == NodeState.PENDING

    def test_add_node_dependency_not_exists(self, client: CascadeClient):
        client.add("root")
        result = client.add(
            "new_task",
            deps={
                "non_existent": Contract(
                    "Expect output from non_existent", "Promise output to dependent"
                )
            },
        )
        assert result.success is False
        assert "not found" in result.message

    def test_independent_subgraphs_allowed(self, client: CascadeClient, temp_storage):
        """Multiple independent task groups are allowed."""
        result = client.add("group_a_root")
        assert result.success is True

        result = client.add("group_b_root")
        assert result.success is True

        with temp_storage.lock():
            cascade = temp_storage.load()
            assert "group_a_root" in cascade.nodes
            assert "group_b_root" in cascade.nodes
            assert cascade.nodes["group_a_root"].state == NodeState.READY
            assert cascade.nodes["group_b_root"].state == NodeState.READY

    def test_add_node_with_dependents(self, client: CascadeClient, temp_storage):
        client.add("root")
        client.add(
            "child",
            deps={"root": Contract("Expect output from root", "Promise output to dependent")},
        )

        result = client.add(
            "new_parent",
            dependents={"child": Contract("Child expects input", "New parent provides input")},
        )
        assert result.success is True

        with temp_storage.lock():
            cascade = temp_storage.load()
            assert cascade.pending_dependency_count("child") == 2

    def test_independent_subgraph_with_deps(self, client: CascadeClient):
        """Independent subgraphs can each have their own dependency chains."""
        client.add("root")
        client.add(
            "child",
            deps={"root": Contract("Expect output from root", "Promise output to dependent")},
        )

        result = client.add("other_root")
        assert result.success is True


class TestRefineNode:
    """Tests for refine (formerly refine_node)."""

    def test_refine_node(self, client: CascadeClient, temp_storage):
        client.add("root")
        client.add(
            "task_a",
            deps={"root": Contract("Expect output from root", "Promise output to dependent")},
        )
        client.add(
            "task_b",
            deps={"root": Contract("Expect output from root", "Promise output to dependent")},
        )

        result = client.refine(
            "task_b",
            "task_a",
            expectation="Expect output from task_a",
            promise="Promise to provide results",
        )
        assert result.success is True

        with temp_storage.lock():
            cascade = temp_storage.load()
            assert cascade.pending_dependency_count("task_b") == 2

    def test_refine_node_requires_contract(self, client: CascadeClient):
        client.add("root")
        client.add(
            "task_a",
            deps={"root": Contract("Expect output from root", "Promise output to dependent")},
        )

        result = client.refine("task_a", "root", expectation="", promise="some promise")
        assert result.success is False
        assert "expectation" in result.message.lower()

        result = client.refine("task_a", "root", expectation="some expectation", promise="")
        assert result.success is False
        assert "promise" in result.message.lower()


class TestRemoveNode:
    """Tests for remove (formerly remove_node)."""

    def test_remove_node(self, client: CascadeClient, temp_storage):
        client.add("root")
        client.add(
            "task_a",
            deps={"root": Contract("Expect output from root", "Promise output to dependent")},
        )
        client.add(
            "task_b",
            deps={"task_a": Contract("Expect output from task_a", "Promise output to dependent")},
        )

        result = client.remove("task_b")
        assert result.success is True

        with temp_storage.lock():
            cascade = temp_storage.load()
            assert "task_b" not in cascade.nodes


class TestSplitNode:
    """Tests for split (formerly split_node)."""

    def test_split_node(self, client: CascadeClient, temp_storage):
        client.add("task_a")
        client.add(
            "task_b",
            deps={"task_a": Contract("Expect output from task_a", "Promise output to dependent")},
        )

        result = client.split("task_b", into=["task_b1", "task_b2"])
        assert result.success is True

        with temp_storage.lock():
            cascade = temp_storage.load()
            assert "task_b" not in cascade.nodes
            assert "task_b1" in cascade.nodes


class TestListNodes:
    """Tests for nodes (formerly list_nodes)."""

    def test_list_all_nodes(self, client: CascadeClient):
        client.add("root")
        client.add(
            "task_a",
            deps={"root": Contract("Expect output from root", "Promise output to dependent")},
        )
        client.add(
            "task_b",
            deps={"root": Contract("Expect output from root", "Promise output to dependent")},
        )
        client.add(
            "task_c",
            deps={"root": Contract("Expect output from root", "Promise output to dependent")},
        )

        r = client.nodes()
        assert r.data["count"] == 4

    def test_list_nodes_with_filter(self, client: CascadeClient):
        client.add("task_a")
        client.add(
            "task_b",
            deps={"task_a": Contract("Expect output from task_a", "Promise output to dependent")},
        )

        r = client.nodes(state="READY")
        assert r.data["count"] == 1


class TestCheckTimeouts:
    """Tests for check_timeouts."""

    def test_release_timed_out_task(self, client: CascadeClient, temp_storage):
        client.add("task_a")
        client.claim("agent_1", "task_a", timeout=0.01)

        time.sleep(0.02)

        result = client.check_timeouts()
        assert result.success is True
        assert result.data["count"] == 1
        assert result.data["released"][0]["task_id"] == "task_a"
        assert result.data["released"][0]["agent_id"] == "agent_1"

        with temp_storage.lock():
            cascade = temp_storage.load()
            assert cascade.nodes["task_a"].state == NodeState.READY
            assert cascade.nodes["task_a"].agent_id is None

    def test_no_timeout_no_release(self, client: CascadeClient):
        client.add("task_a")
        client.claim("agent_1", "task_a")

        result = client.check_timeouts()
        assert result.success is True
        assert result.data["count"] == 0

    def test_default_timeout(self, client: CascadeClient, temp_storage):
        client.add("task_a")
        client.claim("agent_1", "task_a")

        # Force claimed_at to the past
        with temp_storage.lock():
            cascade = temp_storage.load()
            cascade.nodes["task_a"].claimed_at = 0.0
            temp_storage.save(cascade)

        result = client.check_timeouts(default_timeout=60)
        assert result.success is True
        assert result.data["count"] == 1

    def test_not_yet_timed_out(self, client: CascadeClient):
        client.add("task_a")
        client.claim("agent_1", "task_a", timeout=3600)

        result = client.check_timeouts()
        assert result.success is True
        assert result.data["count"] == 0
