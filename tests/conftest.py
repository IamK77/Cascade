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

"""Pytest configuration and fixtures."""

import tempfile
from pathlib import Path

import pytest

from cascade.context.context import Context
from cascade.core.cascade import Cascade
from cascade.core.node import Node
from cascade.core.state import NodeState
from cascade.storage.graph_storage import GraphStorage


@pytest.fixture
def temp_storage():
    """Create a temporary GraphStorage for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = GraphStorage(Path(tmpdir))
        yield storage


@pytest.fixture
def empty_cascade():
    """Create an empty Cascade."""
    return Cascade()


@pytest.fixture
def sample_cascade():
    """Create a sample Cascade with nodes and edges.

    Structure:
        a -> b -> d
        |    |
        v    v
        c -> e
    """
    cascade = Cascade()

    cascade.add_node(Node(id="a", state=NodeState.READY))
    cascade.add_node(Node(id="b", state=NodeState.PENDING))
    cascade.add_node(Node(id="c", state=NodeState.PENDING))
    cascade.add_node(Node(id="d", state=NodeState.PENDING))
    cascade.add_node(Node(id="e", state=NodeState.PENDING))

    cascade.add_edge("a", "b", expectation="Expect output from a", promise="A promises to b")
    cascade.add_edge("a", "c", expectation="Expect output from a", promise="A promises to c")
    cascade.add_edge("b", "d", expectation="Expect output from b", promise="B promises to d")
    cascade.add_edge("b", "e", expectation="Expect output from b", promise="B promises to e")
    cascade.add_edge("c", "e", expectation="Expect output from c", promise="C promises to e")

    return cascade


@pytest.fixture
def sample_cascade_with_context():
    """Create a Cascade with nodes having context."""
    cascade = Cascade()

    context_a = Context(
        critical={"project": "test"},
        summary="Initial task",
        artifacts="# Task A\nThis is the initial task."
    )
    context_b = Context(
        critical={"depends_on": "a"},
        summary="Dependent task",
        artifacts="# Task B\nDepends on A."
    )

    cascade.add_node(Node(id="a", state=NodeState.READY, context=context_a))
    cascade.add_node(Node(id="b", state=NodeState.PENDING, context=context_b))

    cascade.add_edge("a", "b", expectation="Expect output from a", promise="A promises output")

    return cascade


@pytest.fixture
def sample_cascade_with_contracts():
    """Create a Cascade with edges having contract metadata."""
    cascade = Cascade()

    cascade.add_node(Node(id="a", state=NodeState.READY))
    cascade.add_node(Node(id="b", state=NodeState.PENDING))

    cascade.add_edge(
        "a", "b",
        expectation="Expect config results",
        promise="Promise to output config results"
    )

    return cascade


@pytest.fixture
def sample_context():
    """Create a sample context."""
    return Context(
        critical={"key1": "value1", "key2": "value2"},
        summary="This is a summary",
        artifacts="# Full Artifacts\n\nDetailed content here."
    )


@pytest.fixture
def sample_contract():
    """Create a sample contract string."""
    return "Promise to output results containing param1 and param2"


@pytest.fixture
def sample_nodes():
    """Create sample nodes for testing."""
    return [
        Node(id="node1", state=NodeState.READY),
        Node(id="node2", state=NodeState.PENDING),
        Node(id="node3", state=NodeState.PENDING),
    ]
