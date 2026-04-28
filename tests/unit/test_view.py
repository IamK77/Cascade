"""Tests for view.py — get_node_view, render_briefing, render_inspect."""

from cascade import CascadeClient, Contract
from cascade.core.cascade import Cascade
from cascade.view import render_briefing, render_inspect


def _make_client(tmp_path):
    return CascadeClient(str(tmp_path / ".cascade"))


class TestRenderBriefing:
    def test_minimal_task(self, tmp_path):
        c = _make_client(tmp_path)
        c.add("root")
        task = c.claim("w1", task_id="root")
        md = render_briefing(task.raw)
        assert "# Task: root" in md
        assert "## Upstream Context" not in md
        assert "## Promises to Downstream" not in md

    def test_upstream_context(self, tmp_path):
        c = _make_client(tmp_path)
        c.add("analyze")
        c.add("design", deps={"analyze": Contract("Need spec", "Deliver spec")})

        c.claim("w1", task_id="analyze")
        c.complete("analyze", summary="Done", critical={"db": "pg"})

        task = c.claim("w2", task_id="design")
        md = render_briefing(task.raw)

        assert "## Upstream Context" in md
        assert "### analyze (direct dependency)" in md
        assert "**Expects from you**: Need spec" in md
        assert "**Promised to deliver**: Deliver spec" in md
        assert "**Summary**: Done" in md
        assert '"db": "pg"' in md

    def test_ancestor_distance_2(self, tmp_path):
        c = _make_client(tmp_path)
        c.add("root")
        c.add("mid", deps={"root": Contract("E1", "P1")})
        c.add("leaf", deps={"mid": Contract("E2", "P2")})

        c.claim("w1", task_id="root")
        c.complete("root", summary="Root done", critical={"key": "val"})
        c.claim("w2", task_id="mid")
        c.complete("mid", summary="Mid done")

        task = c.claim("w3", task_id="leaf")
        md = render_briefing(task.raw)

        assert "### mid (direct dependency)" in md
        assert "### root (ancestor, distance 2)" in md

    def test_promises_to_downstream(self, tmp_path):
        c = _make_client(tmp_path)
        c.add("impl")
        c.add("integrate", deps={"impl": Contract("Need module", "Deliver implementation")})

        task = c.claim("w1", task_id="impl")
        md = render_briefing(task.raw)

        assert "## Promises to Downstream" in md
        assert "→ **integrate**: Deliver implementation" in md

    def test_fan_in_multiple_upstream(self, tmp_path):
        c = _make_client(tmp_path)
        c.add("auth")
        c.add("api")
        c.add(
            "integrate",
            deps={
                "auth": Contract("Need auth", "Deliver auth module"),
                "api": Contract("Need api", "Deliver api module"),
            },
        )

        c.claim("w1", task_id="auth")
        c.complete("auth", summary="Auth done", critical={"type": "JWT"})
        c.claim("w2", task_id="api")
        c.complete("api", summary="API done", critical={"endpoints": ["/users"]})

        task = c.claim("w3", task_id="integrate")
        md = render_briefing(task.raw)

        assert "### auth (direct dependency)" in md
        assert "### api (direct dependency)" in md
        assert "Auth done" in md
        assert "API done" in md

    def test_artifacts_in_briefing(self, tmp_path):
        c = _make_client(tmp_path)
        c.add("analyze")
        c.add("impl", deps={"analyze": Contract("E", "P")})

        c.claim("w1", task_id="analyze")
        c.complete("analyze", artifacts="# Full Spec\n## Auth\nJWT based")

        task = c.claim("w2", task_id="impl")
        md = render_briefing(task.raw)

        assert "**Artifacts**:" in md
        assert "# Full Spec" in md

    def test_visible_nodes(self, tmp_path):
        c = _make_client(tmp_path)
        c.add("a")
        c.add("b", deps={"a": Contract("E", "P")})
        c.add("c", deps={"b": Contract("E2", "P2")})

        task = c.claim("w1", task_id="a")
        md = render_briefing(task.raw)

        assert "## Downstream Topology" in md
        assert "b" in md

    def test_no_upstream_no_promises(self, tmp_path):
        c = _make_client(tmp_path)
        c.add("standalone")

        task = c.claim("w1", task_id="standalone")
        md = render_briefing(task.raw)

        assert "# Task: standalone" in md
        lines = [line for line in md.split("\n") if line.strip()]
        assert len(lines) == 1

    def test_critical_json_formatting(self, tmp_path):
        c = _make_client(tmp_path)
        c.add("a")
        c.add("b", deps={"a": Contract("E", "P")})

        c.claim("w1", task_id="a")
        c.complete("a", critical={"endpoints": ["/auth", "/users"], "db": "PostgreSQL"})

        task = c.claim("w2", task_id="b")
        md = render_briefing(task.raw)

        assert "```json" in md
        assert '"/auth"' in md
        assert '"PostgreSQL"' in md


class TestRenderInspect:
    def test_inspect_unknown_node(self, tmp_path):
        c = _make_client(tmp_path)
        graph = c._storage.load() or Cascade()
        out = render_inspect(graph, "ghost")
        assert "not found" in out

    def test_inspect_completed_shows_delivered(self, tmp_path):
        c = _make_client(tmp_path)
        c.add("a")
        c.claim("w1", task_id="a")
        c.complete("a", summary="Done", critical={"k": "v"}, artifacts="# Spec")

        graph = c._storage.load()
        out = render_inspect(graph, "a")

        assert "_State: COMPLETED_" in out
        assert "## Delivered" in out
        assert "**Summary**: Done" in out
        assert '"k": "v"' in out
        assert "**Artifacts**: # Spec" in out

    def test_inspect_ready_no_delivered_section(self, tmp_path):
        c = _make_client(tmp_path)
        c.add("a")
        graph = c._storage.load()
        out = render_inspect(graph, "a")

        assert "_State: READY_" in out
        assert "## Delivered" not in out

    def test_inspect_completed_without_context(self, tmp_path):
        c = _make_client(tmp_path)
        c.add("a")
        c.claim("w1", task_id="a")
        c.complete("a")  # no summary/critical/artifacts

        graph = c._storage.load()
        out = render_inspect(graph, "a")

        assert "## Delivered" in out
        assert "No context delivered" in out

    def test_inspect_includes_upstream_briefing(self, tmp_path):
        c = _make_client(tmp_path)
        c.add("up")
        c.add("down", deps={"up": Contract("E", "P")})
        c.claim("w1", task_id="up")
        c.complete("up", summary="Up done", critical={"x": 1})

        graph = c._storage.load()
        out = render_inspect(graph, "down")

        assert "## Upstream Context" in out
        assert "Up done" in out
        assert "_State: READY_" in out
