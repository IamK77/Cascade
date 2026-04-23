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

"""Tests for Cascade storage."""

import json
import tempfile
from pathlib import Path

import pytest

from cascade.context.context import Context
from cascade.core.cascade import Cascade
from cascade.core.node import Node
from cascade.core.state import NodeState
from cascade.storage.graph_storage import GraphStorage


class TestGraphStorage:
    """Tests for GraphStorage."""

    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as d:
            yield Path(d)

    @pytest.fixture
    def storage(self, temp_dir):
        return GraphStorage(base_dir=temp_dir)

    @pytest.fixture
    def sample_cascade(self):
        cascade = Cascade()
        node_a = Node(
            id="a",
            state=NodeState.READY,
            context=Context(critical={"project": "test"}, summary="This is node A"),
        )
        node_b = Node(id="b", state=NodeState.PENDING)
        cascade.add_node(node_a)
        cascade.add_node(node_b)
        cascade.add_edge(
            "a",
            "b",
            expectation="Expect analysis results",
            promise="Promises to output analysis results",
        )
        return cascade

    def test_save_and_load(self, storage, sample_cascade):
        storage.save(sample_cascade)
        assert storage.exists()

        loaded = storage.load()
        assert loaded is not None
        assert len(loaded.nodes) == 2
        assert "a" in loaded.nodes
        assert "b" in loaded.nodes

    def test_load_nonexistent(self, storage):
        assert storage.load() is None

    def test_save_preserves_node_state(self, storage, sample_cascade):
        storage.save(sample_cascade)
        loaded = storage.load()
        assert loaded.nodes["a"].state == NodeState.READY
        assert loaded.nodes["b"].state == NodeState.PENDING

    def test_save_preserves_context(self, storage, sample_cascade):
        storage.save(sample_cascade)
        loaded = storage.load()
        assert loaded.nodes["a"].context is not None
        assert loaded.nodes["a"].context.critical == {"project": "test"}
        assert loaded.nodes["a"].context.summary == "This is node A"

    def test_save_preserves_contracts(self, storage, sample_cascade):
        storage.save(sample_cascade)
        loaded = storage.load()

        contract = loaded.get_contract("a", "b")
        assert contract is not None
        assert contract.expectation == "Expect analysis results"
        assert contract.promise == "Promises to output analysis results"

    def test_save_preserves_edges(self, storage, sample_cascade):
        storage.save(sample_cascade)
        loaded = storage.load()
        dependents = loaded.get_dependents("a")
        assert len(dependents) == 1
        assert dependents[0].id == "b"

    def test_save_node_incremental(self, storage, sample_cascade):
        storage.save(sample_cascade)
        sample_cascade.nodes["a"].context = Context(
            critical={"project": "updated"},
            summary="Updated summary",
        )
        storage.save_node(sample_cascade, "a")

        loaded = storage.load()
        assert loaded.nodes["a"].context.summary == "Updated summary"
        assert "b" in loaded.nodes

    def test_delete(self, storage, sample_cascade):
        storage.save(sample_cascade)
        assert storage.exists()
        storage.delete()
        assert not storage.exists()

    def test_empty_cascade(self, storage):
        cascade = Cascade()
        storage.save(cascade)
        loaded = storage.load()
        assert loaded is not None
        assert len(loaded.nodes) == 0

    def test_node_without_context(self, storage):
        cascade = Cascade()
        cascade.add_node(Node(id="test", state=NodeState.READY))
        storage.save(cascade)
        loaded = storage.load()
        assert loaded.nodes["test"].context is None

    def test_artifacts_saved_as_file(self, storage, temp_dir):
        cascade = Cascade()
        artifacts_content = "# Task Artifacts\n\nThis is the full documentation."
        node = Node(
            id="task_a",
            state=NodeState.READY,
            context=Context(
                critical={"project": "test"}, summary="Task A summary", artifacts=artifacts_content
            ),
        )
        cascade.add_node(node)
        storage.save(cascade)

        artifacts_file = temp_dir / "artifacts" / "task_a.md"
        assert artifacts_file.exists()
        assert artifacts_file.read_text(encoding="utf-8") == artifacts_content

        graph_data = json.loads((temp_dir / "graph.json").read_text(encoding="utf-8"))
        assert (
            graph_data["nodes"]["task_a"]["context"]["artifacts"] == ".cascade/artifacts/task_a.md"
        )

    def test_artifacts_loaded_from_file(self, storage):
        cascade = Cascade()
        artifacts_content = "# Detailed Documentation\n\nFull content here."
        node = Node(
            id="doc_node", state=NodeState.READY, context=Context(artifacts=artifacts_content)
        )
        cascade.add_node(node)
        storage.save(cascade)

        loaded = storage.load()
        assert loaded.nodes["doc_node"].context is not None
        assert loaded.nodes["doc_node"].context.artifacts == artifacts_content

    def test_artifacts_round_trip(self, storage, temp_dir):
        """Test that artifacts content round-trips through save/load."""
        cascade = Cascade()
        content = "# Existing Artifacts\n\nPre-created content."
        node = Node(
            id="pre_node",
            state=NodeState.READY,
            context=Context(artifacts=content),
        )
        cascade.add_node(node)
        storage.save(cascade)

        # Verify file was created
        artifacts_file = temp_dir / "artifacts" / "pre_node.md"
        assert artifacts_file.exists()
        assert artifacts_file.read_text(encoding="utf-8") == content

        # Verify round-trip
        loaded = storage.load()
        assert loaded.nodes["pre_node"].context.artifacts == content

    def test_save_preserves_agent_id(self, storage):
        cascade = Cascade()
        node = Node(id="task", state=NodeState.ACTIVE, agent_id="agent-001")
        cascade.add_node(node)
        storage.save(cascade)
        loaded = storage.load()
        assert loaded.nodes["task"].agent_id == "agent-001"

    def test_agent_tasks_index(self, storage):
        cascade = Cascade()
        cascade.add_node(Node(id="task_a", state=NodeState.ACTIVE, agent_id="agent-001"))
        cascade.add_node(Node(id="task_b", state=NodeState.PENDING))
        storage.save(cascade)

        graph_data = json.loads((storage.base_dir / "graph.json").read_text())
        assert "agent_tasks" in graph_data
        assert graph_data["agent_tasks"]["agent-001"] == "task_a"
