"""Tests for view.py — get_node_view, render_briefing, render_inspect."""

from conftest import auto_deliverables, claim_token

from cascade import CascadeClient, Contract
from cascade.core.cascade import Cascade
from cascade.view import render_briefing, render_inspect


def _make_client(tmp_path):
    return CascadeClient(str(tmp_path / ".cascade"))


def _claim_view(client, agent_id, task_id=None):
    """Claim and return task_info dict for render_briefing tests."""
    r = client.claim(agent_id, task_id=task_id)
    return r.data.get("task_info", {})


class TestRenderBriefing:
    def test_minimal_task(self, tmp_path):
        c = _make_client(tmp_path)
        c.add("root")
        md = render_briefing(_claim_view(c, "w1", task_id="root"))
        assert "Task: root" in md
        assert "[upstream:" not in md
        assert "[promises]" not in md

    def test_upstream_context(self, tmp_path):
        c = _make_client(tmp_path)
        c.add("analyze")
        c.add("design", deps={"analyze": Contract("Need spec", "Deliver spec")})

        _t = claim_token(c, "w1", "analyze")
        c.complete(
            "analyze",
            summary="Done",
            critical={"db": "pg"},
            token=_t,
            deliverables=auto_deliverables(c, "analyze"),
        )

        md = render_briefing(_claim_view(c, "w2", task_id="design"))

        assert "[upstream: analyze, direct]" in md
        assert "you expected: Need spec" in md
        assert "analyze promised: Deliver spec" in md
        assert "summary: Done" in md
        assert '"db": "pg"' in md

    def test_ancestor_distance_2(self, tmp_path):
        c = _make_client(tmp_path)
        c.add("root")
        c.add("mid", deps={"root": Contract("E1", "P1")})
        c.add("leaf", deps={"mid": Contract("E2", "P2")})

        _t = claim_token(c, "w1", "root")
        c.complete(
            "root",
            summary="Root done",
            critical={"key": "val"},
            token=_t,
            deliverables=auto_deliverables(c, "root"),
        )
        _t = claim_token(c, "w2", "mid")
        c.complete("mid", summary="Mid done", token=_t, deliverables=auto_deliverables(c, "mid"))

        md = render_briefing(_claim_view(c, "w3", task_id="leaf"))

        assert "[upstream: mid, direct]" in md
        assert "[upstream: root, distance 2]" in md

    def test_promises_to_downstream(self, tmp_path):
        c = _make_client(tmp_path)
        c.add("impl")
        c.add("integrate", deps={"impl": Contract("Need module", "Deliver implementation")})

        md = render_briefing(_claim_view(c, "w1", task_id="impl"))

        assert "[promises]" in md
        assert "integrate expects: Need module" in md
        assert "you promise: Deliver implementation" in md

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

        _t = claim_token(c, "w1", "auth")
        c.complete(
            "auth",
            summary="Auth done",
            critical={"type": "JWT"},
            token=_t,
            deliverables=auto_deliverables(c, "auth"),
        )
        _t = claim_token(c, "w2", "api")
        c.complete(
            "api",
            summary="API done",
            critical={"endpoints": ["/users"]},
            token=_t,
            deliverables=auto_deliverables(c, "api"),
        )

        md = render_briefing(_claim_view(c, "w3", task_id="integrate"))

        assert "[upstream: auth, direct]" in md
        assert "[upstream: api, direct]" in md
        assert "Auth done" in md
        assert "API done" in md

    def test_artifacts_in_briefing(self, tmp_path):
        c = _make_client(tmp_path)
        c.add("analyze")
        c.add("impl", deps={"analyze": Contract("E", "P")})

        _t = claim_token(c, "w1", "analyze")
        c.complete(
            "analyze",
            artifacts="# Full Spec\n## Auth\nJWT based",
            token=_t,
            deliverables=auto_deliverables(c, "analyze"),
        )

        md = render_briefing(_claim_view(c, "w2", task_id="impl"))

        assert "artifacts:" in md
        assert "# Full Spec" in md

    def test_visible_nodes(self, tmp_path):
        c = _make_client(tmp_path)
        c.add("a")
        c.add("b", deps={"a": Contract("E", "P")})
        c.add("c", deps={"b": Contract("E2", "P2")})

        md = render_briefing(_claim_view(c, "w1", task_id="a"))

        assert "[downstream]" in md
        assert "b" in md

    def test_no_upstream_no_promises(self, tmp_path):
        c = _make_client(tmp_path)
        c.add("standalone")

        md = render_briefing(_claim_view(c, "w1", task_id="standalone"))

        assert "Task: standalone" in md
        lines = [line for line in md.split("\n") if line.strip()]
        assert len(lines) == 1

    def test_critical_json_formatting(self, tmp_path):
        c = _make_client(tmp_path)
        c.add("a")
        c.add("b", deps={"a": Contract("E", "P")})

        _t = claim_token(c, "w1", "a")
        c.complete(
            "a",
            critical={"endpoints": ["/auth", "/users"], "db": "PostgreSQL"},
            token=_t,
            deliverables=auto_deliverables(c, "a"),
        )

        md = render_briefing(_claim_view(c, "w2", task_id="b"))

        assert "critical:" in md
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
        _t = claim_token(c, "w1", "a")
        c.complete("a", summary="Done", critical={"k": "v"}, artifacts="# Spec", token=_t)

        graph = c._storage.load()
        out = render_inspect(graph, "a")

        assert "state: COMPLETED" in out
        assert "[delivered by this node]" in out
        assert "summary: Done" in out
        assert '"k": "v"' in out
        assert "artifacts:" in out
        assert "|# Spec" in out

    def test_inspect_ready_no_delivered_section(self, tmp_path):
        c = _make_client(tmp_path)
        c.add("a")
        graph = c._storage.load()
        out = render_inspect(graph, "a")

        assert "state: READY" in out
        assert "[delivered" not in out

    def test_inspect_completed_without_user_context(self, tmp_path):
        c = _make_client(tmp_path)
        c.add("a")
        _t = claim_token(c, "w1", "a")
        c.complete("a", token=_t)

        graph = c._storage.load()
        out = render_inspect(graph, "a")

        assert "[delivered by this node]" in out
        assert "freshness:" in out
        assert "critical:" not in out
        assert "summary:" not in out

    def test_inspect_includes_upstream_briefing(self, tmp_path):
        c = _make_client(tmp_path)
        c.add("up")
        c.add("down", deps={"up": Contract("E", "P")})
        _t = claim_token(c, "w1", "up")
        c.complete(
            "up",
            summary="Up done",
            critical={"x": 1},
            token=_t,
            deliverables=auto_deliverables(c, "up"),
        )

        graph = c._storage.load()
        out = render_inspect(graph, "down")

        assert "[upstream: up, direct]" in out
        assert "Up done" in out
        assert "state: READY" in out
