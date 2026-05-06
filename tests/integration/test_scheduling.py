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

"""Tests for critical path scheduling and DAG visualization."""

from cascade.core.cascade import Cascade
from cascade.core.node import Node
from cascade.core.state import NodeState
from cascade.viz import to_ascii, to_mermaid


class TestCriticalPath:
    """Tests for critical path computation and scheduling."""

    def test_linear_chain_critical_path(self):
        """In a linear chain, the critical path is the whole chain."""
        cascade = Cascade()
        cascade.add_node(Node(id="a"))
        cascade.add_node(Node(id="b"))
        cascade.add_node(Node(id="c"))
        cascade.add_edge("a", "b", expectation="E", promise="P")
        cascade.add_edge("b", "c", expectation="E", promise="P")

        path = cascade.get_critical_path()
        assert path == ["a", "b", "c"]

    def test_diamond_critical_path(self):
        """In a diamond, critical path goes through the longer branch."""
        #     a
        #    / \
        #   b   c
        #   |   |
        #   d   |
        #    \ /
        #     e
        cascade = Cascade()
        cascade.add_node(Node(id="a"))
        cascade.add_node(Node(id="b"))
        cascade.add_node(Node(id="c"))
        cascade.add_node(Node(id="d"))
        cascade.add_node(Node(id="e"))
        cascade.add_edge("a", "b", expectation="E", promise="a delivers to b")
        cascade.add_edge("a", "c", expectation="E", promise="a delivers to c")
        cascade.add_edge("b", "d", expectation="E", promise="b delivers to d")
        cascade.add_edge("d", "e", expectation="E", promise="d delivers to e")
        cascade.add_edge("c", "e", expectation="E", promise="c delivers to e")

        path = cascade.get_critical_path()
        # Longer path: a -> b -> d -> e (length 4) vs a -> c -> e (length 3)
        assert path == ["a", "b", "d", "e"]

    def test_completed_nodes_not_on_critical_path(self):
        """Completed nodes are excluded from critical path depth."""
        cascade = Cascade()
        cascade.add_node(Node(id="a", state=NodeState.COMPLETED))
        cascade.add_node(Node(id="b"))
        cascade.add_node(Node(id="c"))
        cascade.add_edge("a", "b", expectation="E", promise="P")
        cascade.add_edge("b", "c", expectation="E", promise="P")

        path = cascade.get_critical_path()
        # a is completed, so critical path is b -> c
        assert path == ["b", "c"]

    def test_scheduling_prioritizes_critical_path(self):
        """get_ready_nodes should prioritize nodes on the critical path."""
        #   a (READY, depth=2: a->b->c)
        #   d (READY, depth=0: leaf)
        cascade = Cascade()
        cascade.add_node(Node(id="a"))
        cascade.add_node(Node(id="b"))
        cascade.add_node(Node(id="c"))
        cascade.add_node(Node(id="d"))
        cascade.add_edge("a", "b", expectation="E", promise="P")
        cascade.add_edge("b", "c", expectation="E", promise="P")

        ready = cascade.get_ready_nodes()
        # a should come before d because a has deeper downstream
        assert len(ready) == 2
        assert ready[0].id == "a"
        assert ready[1].id == "d"

    def test_scheduling_without_prioritization(self):
        """get_ready_nodes(prioritize=False) returns unordered."""
        cascade = Cascade()
        cascade.add_node(Node(id="a"))
        cascade.add_node(Node(id="b"))
        cascade.add_node(Node(id="c"))
        cascade.add_edge("a", "b", expectation="E", promise="P")

        ready = cascade.get_ready_nodes(prioritize=False)
        assert len(ready) == 2
        ids = {n.id for n in ready}
        assert ids == {"a", "c"}

    def test_empty_graph_critical_path(self):
        cascade = Cascade()
        assert cascade.get_critical_path() == []

    def test_single_node_critical_path(self):
        cascade = Cascade()
        cascade.add_node(Node(id="only"))
        assert cascade.get_critical_path() == ["only"]


class TestVisualization:
    """Tests for DAG visualization."""

    def test_mermaid_basic(self):
        cascade = Cascade()
        cascade.add_node(Node(id="a", state=NodeState.READY))
        cascade.add_node(Node(id="b", state=NodeState.PENDING))
        cascade.add_edge("a", "b", expectation="Expect output", promise="Provide output")

        mermaid = to_mermaid(cascade)
        assert "graph TD" in mermaid
        assert "a" in mermaid
        assert "b" in mermaid
        assert "-->" in mermaid or "==>" in mermaid

    def test_mermaid_with_contracts(self):
        cascade = Cascade()
        cascade.add_node(Node(id="a", state=NodeState.READY))
        cascade.add_node(Node(id="b", state=NodeState.PENDING))
        cascade.add_edge("a", "b", expectation="Expect analysis", promise="Provide analysis")

        mermaid = to_mermaid(cascade, show_contracts=True)
        assert "Expect analysis" in mermaid

    def test_mermaid_critical_path_highlighted(self):
        cascade = Cascade()
        cascade.add_node(Node(id="a"))
        cascade.add_node(Node(id="b"))
        cascade.add_edge("a", "b", expectation="E", promise="P")

        mermaid = to_mermaid(cascade, show_critical_path=True)
        assert "==>" in mermaid  # thick arrow for critical path

    def test_mermaid_empty_graph(self):
        cascade = Cascade()
        mermaid = to_mermaid(cascade)
        assert "No nodes" in mermaid

    def test_mermaid_agent_shown(self):
        cascade = Cascade()
        cascade.add_node(Node(id="task", state=NodeState.ACTIVE, agent_id="agent-1"))
        mermaid = to_mermaid(cascade)
        assert "agent-1" in mermaid

    def test_ascii_basic(self):
        cascade = Cascade()
        cascade.add_node(Node(id="a", state=NodeState.COMPLETED))
        cascade.add_node(Node(id="b", state=NodeState.ACTIVE, agent_id="agent-1"))
        cascade.add_node(Node(id="c", state=NodeState.PENDING))
        cascade.add_edge("a", "b", expectation="E", promise="P")
        cascade.add_edge("b", "c", expectation="E", promise="P")

        ascii_art = to_ascii(cascade)
        assert "a" in ascii_art
        assert "COMPLETED" in ascii_art
        assert "ACTIVE" in ascii_art
        assert "agent-1" in ascii_art
        assert "PENDING" in ascii_art

    def test_ascii_empty(self):
        cascade = Cascade()
        assert "empty" in to_ascii(cascade)

    def test_ascii_critical_path_marked(self):
        cascade = Cascade()
        cascade.add_node(Node(id="a"))
        cascade.add_node(Node(id="b"))
        cascade.add_edge("a", "b", expectation="E", promise="P")

        ascii_art = to_ascii(cascade)
        assert "*" in ascii_art  # critical path marker
