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

"""Unit tests for cascade.view — edge cases, internal helpers, and boundary conditions.

Targets uncovered lines in src/cascade/view.py: get_node_view with missing node,
render_inspect COMPLETED without context, _format_elapsed branches, _commits_behind,
_freshness_parts, _render_freshness_from_prov_dict, and _get_visible_descendants.
"""

from unittest.mock import patch

import pytest

from cascade.context.context import Context
from cascade.core.cascade import Cascade
from cascade.core.node import Node
from cascade.core.state import NodeState
from cascade.errors import NodeNotFoundError
from cascade.types import Contract, Provenance
from cascade.view import (
    _format_elapsed,
    _freshness_parts,
    _get_visible_descendants,
    _render_freshness_from_prov_dict,
    _render_freshness_from_provenance,
    get_node_view,
    render_briefing,
    render_inspect,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _simple_graph(*node_ids: str) -> Cascade:
    """Create a Cascade with the given node IDs, all READY."""
    g = Cascade()
    for nid in node_ids:
        g.add_node(Node(id=nid, state=NodeState.READY))
    return g


def _chain_graph(ids: list[str], contracts: list[Contract] | None = None) -> Cascade:
    """Create a linear chain: ids[0] -> ids[1] -> ... -> ids[-1]."""
    g = Cascade()
    for nid in ids:
        g.add_node(Node(id=nid, state=NodeState.READY if nid == ids[0] else NodeState.PENDING))
    for i in range(len(ids) - 1):
        c = contracts[i] if contracts else Contract(f"E{i}", f"P{i}")
        g.add_edge(ids[i], ids[i + 1], expectation=c.expectation, promise=c.promise)
    return g


# ===========================================================================
# get_node_view
# ===========================================================================


class TestGetNodeView:
    """Tests for get_node_view — the core view builder."""

    def test_raises_on_missing_node(self):
        """Line 44: get_node_view raises NodeNotFoundError for unknown ID."""
        g = _simple_graph("a")
        with pytest.raises(NodeNotFoundError, match="ghost"):
            get_node_view(g, "ghost")

    def test_minimal_node_returns_id_and_state(self):
        """A standalone node has id and state, no upstream/promises/visible_nodes."""
        g = _simple_graph("solo")
        view = get_node_view(g, "solo")
        assert view["id"] == "solo"
        assert view["state"] == "READY"
        assert "upstream" not in view
        assert "promises" not in view
        assert "visible_nodes" not in view

    def test_upstream_populated_for_dependent(self):
        """Dependent node receives upstream entries from completed parent."""
        g = _chain_graph(["parent", "child"], [Contract("Give me X", "I will give X")])
        parent = g.nodes["parent"]
        parent.update_state(NodeState.ACTIVE)
        parent.update_state(NodeState.COMPLETED)
        parent.context = Context(summary="Parent done", critical={"k": "v"})

        view = get_node_view(g, "child")
        assert "upstream" in view
        assert len(view["upstream"]) == 1
        entry = view["upstream"][0]
        assert entry["node_id"] == "parent"
        assert entry["distance"] == 1

    def test_promises_populated_for_parent(self):
        """Parent node has promises to its downstream child."""
        g = _chain_graph(["parent", "child"], [Contract("Need it", "Will deliver")])
        view = get_node_view(g, "parent")
        assert "promises" in view
        assert any(p["to_node"] == "child" for p in view["promises"])

    def test_visible_descendants_populated(self):
        """Node with dependents should have visible_nodes in view."""
        g = _chain_graph(["a", "b", "c"])
        view = get_node_view(g, "a")
        assert "visible_nodes" in view

    def test_delivered_context_includes_provenance(self):
        """Upstream with provenance includes it in delivered dict."""
        g = _chain_graph(["up", "down"], [Contract("E", "P")])
        up = g.nodes["up"]
        up.update_state(NodeState.ACTIVE)
        up.update_state(NodeState.COMPLETED)
        up.context = Context(
            summary="Done",
            provenance=Provenance(produced_at=1000.0, deliverables={"down": "Result"}),
        )

        view = get_node_view(g, "down")
        delivered = view["upstream"][0].get("delivered", {})
        assert "provenance" in delivered
        assert delivered["provenance"]["produced_at"] == 1000.0

    def test_no_delivered_when_context_empty(self):
        """Upstream node with no context produces no delivered key."""
        g = _chain_graph(["up", "down"], [Contract("E", "P")])
        up = g.nodes["up"]
        up.update_state(NodeState.ACTIVE)
        up.update_state(NodeState.COMPLETED)
        # context is None by default

        view = get_node_view(g, "down")
        # No upstream entries since parent has no context
        assert view.get("upstream", []) == []


# ===========================================================================
# render_inspect
# ===========================================================================


class TestRenderInspect:
    """Tests for render_inspect — read-only review tool."""

    def test_completed_without_context_shows_no_context_delivered(self):
        """Lines 122-125: COMPLETED node with no context shows '(no context delivered)'."""
        g = _simple_graph("x")
        node = g.nodes["x"]
        node.update_state(NodeState.ACTIVE)
        node.update_state(NodeState.COMPLETED)
        # node.context is None — no context was ever set

        out = render_inspect(g, "x")
        assert "state: COMPLETED" in out
        assert "[delivered by this node]" in out
        assert "(no context delivered)" in out

    def test_completed_with_empty_context_shows_no_context_delivered(self):
        """COMPLETED node with Context() but all fields empty."""
        g = _simple_graph("x")
        node = g.nodes["x"]
        node.update_state(NodeState.ACTIVE)
        node.update_state(NodeState.COMPLETED)
        node.context = Context()  # all defaults, no provenance

        out = render_inspect(g, "x")
        assert "[delivered by this node]" in out
        assert "(no context delivered)" in out

    def test_inspect_with_artifacts_shows_indented_content(self):
        """Artifacts are indented with |."""
        g = _simple_graph("a")
        node = g.nodes["a"]
        node.update_state(NodeState.ACTIVE)
        node.update_state(NodeState.COMPLETED)
        node.context = Context(artifacts="line1\nline2")

        out = render_inspect(g, "a")
        assert "artifacts:" in out
        assert "|line1" in out
        assert "|line2" in out

    def test_inspect_with_provenance_freshness(self):
        """Provenance with produced_at renders freshness."""
        import time

        g = _simple_graph("a")
        node = g.nodes["a"]
        node.update_state(NodeState.ACTIVE)
        node.update_state(NodeState.COMPLETED)
        node.context = Context(provenance=Provenance(produced_at=time.time() - 30))

        out = render_inspect(g, "a")
        assert "freshness:" in out
        assert "ago" in out

    def test_inspect_active_no_delivered_section(self):
        """ACTIVE node without context does not show delivered section."""
        g = _simple_graph("a")
        node = g.nodes["a"]
        node.update_state(NodeState.ACTIVE)

        out = render_inspect(g, "a")
        assert "state: ACTIVE" in out
        assert "[delivered" not in out


# ===========================================================================
# _format_elapsed
# ===========================================================================


class TestFormatElapsed:
    """Tests for _format_elapsed — human-readable duration formatting."""

    def test_seconds_only(self):
        """Under 60 seconds: '42s ago'."""
        assert _format_elapsed(42.0) == "42s ago"

    def test_zero_seconds(self):
        assert _format_elapsed(0.0) == "0s ago"

    def test_exactly_60_seconds(self):
        """Line 135-137: 60s = '1m ago' (sec==0 branch)."""
        assert _format_elapsed(60.0) == "1m ago"

    def test_minutes_with_seconds(self):
        """Line 137: 90s = '1m 30s ago'."""
        assert _format_elapsed(90.0) == "1m 30s ago"

    def test_minutes_without_seconds(self):
        """Line 137: exact minutes, no seconds remainder."""
        assert _format_elapsed(120.0) == "2m ago"

    def test_exactly_one_hour(self):
        """Line 138-141: 3600s = '1h ago' (m==0 branch)."""
        assert _format_elapsed(3600.0) == "1h ago"

    def test_hours_with_minutes(self):
        """Line 141: hours with minutes remainder."""
        assert _format_elapsed(3660.0) == "1h 1m ago"

    def test_hours_without_minutes(self):
        """Line 141: exact hours, no minutes remainder."""
        assert _format_elapsed(7200.0) == "2h ago"

    def test_exactly_one_day(self):
        """Line 142-144: 86400s = '1d ago' (h==0 branch)."""
        assert _format_elapsed(86400.0) == "1d ago"

    def test_days_with_hours(self):
        """Line 144: days with hours remainder."""
        assert _format_elapsed(90000.0) == "1d 1h ago"

    def test_days_without_hours(self):
        """Line 144: exact days, no hours remainder."""
        assert _format_elapsed(172800.0) == "2d ago"

    def test_large_value(self):
        """Very large elapsed time."""
        result = _format_elapsed(604800.0)
        assert "7d" in result

    def test_boundary_59_seconds(self):
        assert _format_elapsed(59.0) == "59s ago"

    def test_boundary_3599_seconds(self):
        """Just under 1 hour."""
        assert _format_elapsed(3599.0) == "59m 59s ago"

    def test_boundary_86399_seconds(self):
        """Just under 1 day."""
        assert _format_elapsed(86399.0) == "23h 59m ago"


# ===========================================================================
# _commits_behind
# ===========================================================================


class TestCommitsBehind:
    """Tests for _commits_behind — git integration."""

    def test_commits_behind_success(self):
        """Lines 158-160: successful git rev-list returns int."""
        from cascade.view import _commits_behind

        with patch("cascade.view.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "5\n"
            result = _commits_behind("abc123")
        assert result == 5

    def test_commits_behind_zero(self):
        """git ref at HEAD returns 0."""
        from cascade.view import _commits_behind

        with patch("cascade.view.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "0\n"
            result = _commits_behind("abc123")
        assert result == 0

    def test_commits_behind_failure(self):
        """Non-zero return code yields None."""
        from cascade.view import _commits_behind

        with patch("cascade.view.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 128
            result = _commits_behind("badref")
        assert result is None

    def test_commits_behind_os_error(self):
        """OSError (git not found) yields None."""
        from cascade.view import _commits_behind

        with patch("cascade.view.subprocess.run", side_effect=OSError("not found")):
            result = _commits_behind("abc123")
        assert result is None

    def test_commits_behind_timeout(self):
        """Timeout yields None."""
        import subprocess

        from cascade.view import _commits_behind

        with patch("cascade.view.subprocess.run", side_effect=subprocess.TimeoutExpired("git", 5)):
            result = _commits_behind("abc123")
        assert result is None


# ===========================================================================
# _freshness_parts
# ===========================================================================


class TestFreshnessParts:
    """Tests for _freshness_parts — builds freshness indicator list."""

    def test_elapsed_only(self):
        """produced_at set, no git_ref."""
        import time

        parts = _freshness_parts(time.time() - 10, "")
        assert len(parts) == 1
        assert "ago" in parts[0]

    def test_git_ref_at_head(self):
        """Line 176: git_ref at HEAD shows 'at HEAD'."""
        with patch("cascade.view._commits_behind", return_value=0):
            parts = _freshness_parts(0, "abc123")
        assert "at HEAD" in parts

    def test_git_ref_commits_behind(self):
        """Line 176: git_ref behind HEAD shows 'N commits behind HEAD'."""
        with patch("cascade.view._commits_behind", return_value=3):
            parts = _freshness_parts(0, "abc123")
        assert "3 commits behind HEAD" in parts

    def test_both_elapsed_and_git_ref(self):
        """Both produced_at and git_ref produce two parts."""
        import time

        with patch("cascade.view._commits_behind", return_value=1):
            parts = _freshness_parts(time.time() - 5, "abc123")
        assert len(parts) == 2
        assert "ago" in parts[0]
        assert "commits behind HEAD" in parts[1]

    def test_neither_elapsed_nor_git_ref(self):
        """No produced_at (0) and empty git_ref produce empty list."""
        parts = _freshness_parts(0, "")
        assert parts == []

    def test_git_ref_fails_returns_none(self):
        """_commits_behind returns None — no git part added."""
        with patch("cascade.view._commits_behind", return_value=None):
            parts = _freshness_parts(0, "abc123")
        assert parts == []


# ===========================================================================
# _render_freshness_from_provenance / _render_freshness_from_prov_dict
# ===========================================================================


class TestRenderFreshness:
    """Tests for freshness rendering from Provenance objects and dicts."""

    def test_from_provenance_empty(self):
        """Empty provenance returns empty string."""
        prov = Provenance()
        result = _render_freshness_from_provenance(prov)
        assert result == ""

    def test_from_provenance_with_produced_at(self):
        """Provenance with produced_at returns 'Ns ago'."""
        import time

        prov = Provenance(produced_at=time.time() - 15)
        result = _render_freshness_from_provenance(prov)
        assert "ago" in result

    def test_from_prov_dict_empty(self):
        """Empty dict returns empty string."""
        result = _render_freshness_from_prov_dict({})
        assert result == ""

    def test_from_prov_dict_with_produced_at(self):
        """Dict with produced_at returns 'Ns ago'."""
        import time

        result = _render_freshness_from_prov_dict({"produced_at": time.time() - 15})
        assert "ago" in result

    def test_from_prov_dict_with_git_ref(self):
        """Dict with git_ref queries commits behind."""
        with patch("cascade.view._commits_behind", return_value=2):
            result = _render_freshness_from_prov_dict({"git_ref": "abc123"})
        assert "2 commits behind HEAD" in result

    def test_from_prov_dict_both_fields_joined(self):
        """Both fields joined with ' | '."""
        import time

        with patch("cascade.view._commits_behind", return_value=0):
            result = _render_freshness_from_prov_dict(
                {"produced_at": time.time() - 10, "git_ref": "abc123"}
            )
        assert " | " in result
        assert "ago" in result
        assert "at HEAD" in result


# ===========================================================================
# render_briefing edge cases
# ===========================================================================


class TestRenderBriefingEdgeCases:
    """Edge cases for render_briefing not covered by test_view.py."""

    def test_upstream_with_deliverables(self):
        """Deliverables for this node are rendered as 'X delivered: ...'."""
        view = {
            "id": "child",
            "state": "READY",
            "upstream": [
                {
                    "node_id": "parent",
                    "distance": 1,
                    "delivered": {
                        "provenance": {
                            "deliverables": {"child": "Here is the result"},
                        },
                    },
                }
            ],
        }
        md = render_briefing(view)
        assert "parent delivered: Here is the result" in md

    def test_upstream_deliverables_for_other_node(self):
        """Deliverables for a different node are NOT rendered."""
        view = {
            "id": "child",
            "state": "READY",
            "upstream": [
                {
                    "node_id": "parent",
                    "distance": 1,
                    "delivered": {
                        "provenance": {
                            "deliverables": {"other_child": "Not for me"},
                        },
                    },
                }
            ],
        }
        md = render_briefing(view)
        assert "delivered:" not in md

    def test_upstream_distance_label(self):
        """Distance > 1 shows 'distance N' instead of 'direct'."""
        view = {
            "id": "leaf",
            "state": "READY",
            "upstream": [
                {"node_id": "root", "distance": 3},
            ],
        }
        md = render_briefing(view)
        assert "[upstream: root, distance 3]" in md

    def test_downstream_sorted_by_distance(self):
        """Line 237: visible_nodes are sorted by distance key."""
        view = {
            "id": "a",
            "state": "READY",
            "visible_nodes": {
                "2": [{"id": "c", "state": "PENDING"}],
                "1": [{"id": "b", "state": "PENDING"}],
            },
        }
        md = render_briefing(view)
        assert "[downstream]" in md
        # b at distance 1 should appear before c at distance 2
        b_pos = md.index("b (PENDING, distance 1)")
        c_pos = md.index("c (PENDING, distance 2)")
        assert b_pos < c_pos

    def test_multiple_promises(self):
        """Multiple promises separated by blank line."""
        view = {
            "id": "core",
            "state": "READY",
            "promises": [
                {"to_node": "ui", "expectation": "API contract", "promise": "Stable API"},
                {"to_node": "db", "expectation": "Schema", "promise": "Migration scripts"},
            ],
        }
        md = render_briefing(view)
        assert "ui expects: API contract" in md
        assert "db expects: Schema" in md
        # Second promise block should have blank separator
        lines = md.split("\n")
        promise_lines = [i for i, line in enumerate(lines) if "expects:" in line]
        assert len(promise_lines) == 2
        # There should be a blank line between the two promise groups
        assert any(lines[i].strip() == "" for i in range(promise_lines[0] + 1, promise_lines[1]))

    def test_empty_view(self):
        """View with only id and state produces just 'Task: ...'."""
        view = {"id": "lonely", "state": "READY"}
        md = render_briefing(view)
        assert md == "Task: lonely"

    def test_upstream_with_freshness_from_prov_dict(self):
        """Upstream provenance dict with produced_at renders freshness."""
        import time

        view = {
            "id": "child",
            "state": "READY",
            "upstream": [
                {
                    "node_id": "parent",
                    "distance": 1,
                    "delivered": {
                        "provenance": {"produced_at": time.time() - 60},
                    },
                }
            ],
        }
        md = render_briefing(view)
        assert "freshness:" in md
        assert "ago" in md


# ===========================================================================
# _get_visible_descendants
# ===========================================================================


class TestGetVisibleDescendants:
    """Tests for _get_visible_descendants — BFS topology discovery."""

    def test_no_descendants(self):
        """Leaf node has no visible descendants."""
        g = _simple_graph("leaf")
        result = _get_visible_descendants(g, "leaf")
        assert result == {}

    def test_direct_descendant(self):
        """Distance-1 descendant appears under key '1'."""
        g = _chain_graph(["a", "b"])
        result = _get_visible_descendants(g, "a")
        assert "1" in result
        assert result["1"][0]["id"] == "b"

    def test_two_hop_descendant(self):
        """Distance-2 descendant appears under key '2'."""
        g = _chain_graph(["a", "b", "c"])
        result = _get_visible_descendants(g, "a")
        assert "1" in result
        assert "2" in result
        ids_at_2 = [n["id"] for n in result["2"]]
        assert "c" in ids_at_2

    def test_three_hop_excluded(self):
        """Default max_distance=2 excludes distance-3 nodes."""
        g = _chain_graph(["a", "b", "c", "d"])
        result = _get_visible_descendants(g, "a")
        assert "3" not in result

    def test_custom_max_distance(self):
        """Can override max_distance."""
        g = _chain_graph(["a", "b", "c", "d"])
        result = _get_visible_descendants(g, "a", max_distance=3)
        assert "3" in result
        ids_at_3 = [n["id"] for n in result["3"]]
        assert "d" in ids_at_3

    def test_descendant_includes_expectations(self):
        """Descendant with contracts shows expectations."""
        g = _chain_graph(["a", "b"], [Contract("Need X", "Will give X")])
        result = _get_visible_descendants(g, "a")
        node_info = result["1"][0]
        assert "expectations" in node_info
        assert node_info["expectations"][0]["expectation"] == "Need X"

    def test_fan_out(self):
        """Multiple direct descendants all appear at distance 1."""
        g = Cascade()
        g.add_node(Node(id="root", state=NodeState.READY))
        g.add_node(Node(id="c1", state=NodeState.PENDING))
        g.add_node(Node(id="c2", state=NodeState.PENDING))
        g.add_edge("root", "c1", expectation="E1", promise="P1")
        g.add_edge("root", "c2", expectation="E2", promise="P2")

        result = _get_visible_descendants(g, "root")
        ids_at_1 = {n["id"] for n in result["1"]}
        assert ids_at_1 == {"c1", "c2"}

    def test_diamond_topology(self):
        """Diamond graph: a -> b, a -> c, b -> d, c -> d."""
        g = Cascade()
        for nid in ("a", "b", "c", "d"):
            g.add_node(Node(id=nid, state=NodeState.READY if nid == "a" else NodeState.PENDING))
        g.add_edge("a", "b", expectation="E1", promise="P1")
        g.add_edge("a", "c", expectation="E2", promise="P2")
        g.add_edge("b", "d", expectation="E3", promise="P3")
        g.add_edge("c", "d", expectation="E4", promise="P4")

        result = _get_visible_descendants(g, "a")
        assert "1" in result
        assert "2" in result
        ids_at_1 = {n["id"] for n in result["1"]}
        ids_at_2 = {n["id"] for n in result["2"]}
        assert ids_at_1 == {"b", "c"}
        assert ids_at_2 == {"d"}
