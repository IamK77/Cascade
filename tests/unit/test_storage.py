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

import pytest
import tempfile
from pathlib import Path

from cascade.core.cascade import Cascade
from cascade.core.node import Node
from cascade.core.state import NodeState
from cascade.context.context import Context
from cascade.storage.graph_storage import GraphStorage


class TestGraphStorage:
    """Tests for GraphStorage."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for storage."""
        with tempfile.TemporaryDirectory() as d:
            yield Path(d)

    @pytest.fixture
    def storage(self, temp_dir):
        """Create a storage instance with temp directory."""
        return GraphStorage(base_dir=temp_dir)

    @pytest.fixture
    def sample_cascade(self):
        """Create a sample Cascade for testing."""
        cascade = Cascade()

        node_a = Node(
            id="a",
            state=NodeState.READY,
            context=Context(
                critical={"project": "test"},
                summary="This is node A",
            ),
        )
        node_b = Node(
            id="b",
            state=NodeState.PENDING,
        )

        cascade.add_node(node_a)
        cascade.add_node(node_b)

        # Add dependency with contract on edge
        cascade.add_edge(
            "a", "b",
            expectation="Expect analysis results",
            promise="Promises to output analysis results",
        )

        return cascade

    def test_save_and_load(self, storage, sample_cascade):
        """Test saving and loading a Cascade."""
        storage.save(sample_cascade)

        assert storage.exists()

        loaded_cascade = storage.load()
        assert loaded_cascade is not None
        assert len(loaded_cascade.nodes) == 2
        assert "a" in loaded_cascade.nodes
        assert "b" in loaded_cascade.nodes

    def test_load_nonexistent(self, storage):
        """Test loading when no saved data exists."""
        assert storage.load() is None

    def test_save_preserves_node_state(self, storage, sample_cascade):
        """Test that node state is preserved."""
        storage.save(sample_cascade)
        loaded_cascade = storage.load()

        assert loaded_cascade.nodes["a"].state == NodeState.READY
        assert loaded_cascade.nodes["b"].state == NodeState.PENDING

    def test_save_preserves_context(self, storage, sample_cascade):
        """Test that context is preserved."""
        storage.save(sample_cascade)
        loaded_cascade = storage.load()

        assert loaded_cascade.nodes["a"].context is not None
        assert loaded_cascade.nodes["a"].context.critical == {"project": "test"}
        assert loaded_cascade.nodes["a"].context.summary == "This is node A"

    def test_save_preserves_edge_metadata(self, storage, sample_cascade):
        """Test that edge metadata (contracts) is preserved."""
        storage.save(sample_cascade)
        loaded_cascade = storage.load()

        # Check edge metadata
        edge_metadata = loaded_cascade.get_edge_metadata("a", "b")
        assert edge_metadata["expectation"] == "Expect analysis results"
        assert edge_metadata["promise"] == "Promises to output analysis results"

    def test_save_preserves_edges(self, storage, sample_cascade):
        """Test that edges are preserved."""
        storage.save(sample_cascade)
        loaded_cascade = storage.load()

        dependents = loaded_cascade.get_dependents("a")
        assert len(dependents) == 1
        assert dependents[0].id == "b"

    def test_save_node_incremental(self, storage, sample_cascade):
        """Test incremental node save."""
        # Initial save
        storage.save(sample_cascade)

        # Modify node context
        sample_cascade.nodes["a"].context = Context(
            critical={"project": "updated"},
            summary="Updated summary",
        )

        # Save only the modified node
        storage.save_node(sample_cascade, "a")

        # Load and verify
        loaded_cascade = storage.load()
        assert loaded_cascade.nodes["a"].context.summary == "Updated summary"
        # Other nodes should still be intact
        assert "b" in loaded_cascade.nodes

    def test_delete(self, storage, sample_cascade):
        """Test deleting saved data."""
        storage.save(sample_cascade)
        assert storage.exists()

        storage.delete()
        assert not storage.exists()

    def test_empty_cascade(self, storage):
        """Test saving and loading an empty Cascade."""
        cascade = Cascade()
        storage.save(cascade)

        loaded_cascade = storage.load()
        assert loaded_cascade is not None
        assert len(loaded_cascade.nodes) == 0

    def test_node_without_context(self, storage):
        """Test node without context."""
        cascade = Cascade()
        cascade.add_node(Node(id="test", state=NodeState.READY))

        storage.save(cascade)
        loaded_cascade = storage.load()

        assert loaded_cascade.nodes["test"].context is None

    def test_artifacts_saved_as_file(self, storage, temp_dir):
        """Test that artifacts content is written to a separate file."""
        cascade = Cascade()

        # Create node with artifacts content (must be > 100 chars to trigger file save)
        artifacts_content = "# Task Artifacts\n\nThis is the full documentation for the task with enough content to exceed the threshold limit."
        node = Node(
            id="task_a",
            state=NodeState.READY,
            context=Context(
                critical={"project": "test"},
                summary="Task A summary",
                artifacts=artifacts_content,  # Content, not path
            ),
        )

        cascade.add_node(node)
        storage.save(cascade)

        # Check that artifacts file was created (base_dir is temp_dir, artifacts_dir is temp_dir/artifacts)
        artifacts_file = temp_dir / "artifacts" / "task_a.md"
        assert artifacts_file.exists()

        # Check file content
        file_content = artifacts_file.read_text(encoding="utf-8")
        assert file_content == artifacts_content

        # Check that graph.json contains the path, not the content
        import json
        graph_data = json.loads((temp_dir / "graph.json").read_text(encoding="utf-8"))
        stored_artifacts = graph_data["nodes"]["task_a"]["context"]["artifacts"]
        assert stored_artifacts == ".cascade/artifacts/task_a.md"

    def test_artifacts_loaded_from_file(self, storage, temp_dir):
        """Test that artifacts content is loaded from file."""
        cascade = Cascade()

        artifacts_content = "# Detailed Documentation\n\nFull content here."
        node = Node(
            id="doc_node",
            state=NodeState.READY,
            context=Context(artifacts=artifacts_content),
        )

        cascade.add_node(node)
        storage.save(cascade)

        # Load and verify content is restored
        loaded_cascade = storage.load()
        loaded_context = loaded_cascade.nodes["doc_node"].context

        assert loaded_context is not None
        assert loaded_context.artifacts == artifacts_content

    def test_artifacts_path_preserved(self, storage, temp_dir):
        """Test that when artifacts is already a path, it's preserved."""
        cascade = Cascade()

        # Set artifacts as a path (not content)
        artifacts_path = ".cascade/artifacts/existing.md"
        node = Node(
            id="path_node",
            state=NodeState.READY,
            context=Context(artifacts=artifacts_path),
        )

        cascade.add_node(node)
        storage.save(cascade)

        # Load and verify path is preserved
        loaded_cascade = storage.load()
        loaded_context = loaded_cascade.nodes["path_node"].context

        # Since the file doesn't exist, artifacts should be empty
        assert loaded_context.artifacts == ""

    def test_artifacts_with_existing_file(self, storage, temp_dir):
        """Test loading when artifacts file exists."""
        # Create artifacts file manually (artifacts_dir is temp_dir/artifacts)
        artifacts_dir = temp_dir / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        expected_content = "# Existing Artifacts\n\nPre-created content."
        artifacts_file = artifacts_dir / "preexisting.md"
        artifacts_file.write_text(expected_content, encoding="utf-8")

        # Create node with artifacts path
        cascade = Cascade()
        node = Node(
            id="pre_node",
            state=NodeState.READY,
            context=Context(artifacts=".cascade/artifacts/preexisting.md"),
        )

        cascade.add_node(node)
        storage.save(cascade)

        # Load and verify content is read from file
        loaded_cascade = storage.load()
        loaded_context = loaded_cascade.nodes["pre_node"].context

        assert loaded_context.artifacts == expected_content

    def test_save_preserves_agent_id(self, storage):
        """Test that agent_id is preserved."""
        cascade = Cascade()
        node = Node(id="task", state=NodeState.ACTIVE, agent_id="agent-001")
        cascade.add_node(node)

        storage.save(cascade)
        loaded_cascade = storage.load()

        assert loaded_cascade.nodes["task"].agent_id == "agent-001"

    def test_agent_tasks_index(self, storage):
        """Test that agent_tasks index is saved correctly."""
        cascade = Cascade()
        node_a = Node(id="task_a", state=NodeState.ACTIVE, agent_id="agent-001")
        node_b = Node(id="task_b", state=NodeState.PENDING)
        cascade.add_node(node_a)
        cascade.add_node(node_b)

        storage.save(cascade)

        # Verify agent_tasks in graph.json
        import json
        graph_data = json.loads((storage.base_dir / "graph.json").read_text())
        assert "agent_tasks" in graph_data
        assert graph_data["agent_tasks"]["agent-001"] == "task_a"
