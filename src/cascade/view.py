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

"""Node view construction — presentation layer.

Builds the dict that an LLM agent receives when it claims a task.
This is separated from Cascade because it's presentation concern,
not a graph primitive.
"""

import json
import subprocess
import time
from collections import deque
from typing import Any

from cascade.context.propagator import ContextPropagator
from cascade.core.cascade import Cascade
from cascade.errors import NodeNotFoundError
from cascade.types import DeliveredContext, Provenance, UpstreamEntry


def get_node_view(cascade: Cascade, node_id: str) -> dict[str, Any]:
    """Get all information an agent needs to execute a node.

    Composes data from multiple sources:
    - upstream: each ancestor with contract (if direct) and delivered context
    - promises: what this node owes to downstream dependents
    - visible_nodes: downstream topology (2 hops)
    """
    if node_id not in cascade.nodes:
        raise NodeNotFoundError(f"Node {node_id} not found")

    node = cascade.nodes[node_id]

    propagator = ContextPropagator(cascade)
    entries = propagator.collect_context_at(node_id)

    upstream: list[UpstreamEntry] = []
    for entry in entries:
        item = UpstreamEntry(
            node_id=entry.node_id,
            state=entry.state,
            distance=entry.distance,
            path=entry.path,
        )
        if entry.expectation:
            item["expectation"] = entry.expectation
        if entry.promise:
            item["promise"] = entry.promise

        delivered = DeliveredContext()
        if entry.summary:
            delivered["summary"] = entry.summary
        if entry.critical:
            delivered["critical"] = entry.critical
        if entry.artifacts:
            delivered["artifacts"] = entry.artifacts
        if entry.provenance:
            delivered["provenance"] = entry.provenance.to_dict()
        if delivered:
            item["delivered"] = delivered

        upstream.append(item)

    promises = cascade.get_node_promises(node_id)
    visible_descendants = _get_visible_descendants(cascade, node_id, max_distance=2)

    result: dict[str, Any] = {"id": node.id, "state": node.state.name}
    if upstream:
        result["upstream"] = upstream
    if promises:
        result["promises"] = promises
    if visible_descendants:
        result["visible_nodes"] = visible_descendants

    return result


def render_inspect(cascade: Cascade, node_id: str) -> str:
    """Render a node's briefing plus its own delivered context.

    Read-only review tool — no side effects, no state changes.
    """
    if node_id not in cascade.nodes:
        return f"Task: {node_id} (not found)"

    node = cascade.nodes[node_id]
    view = get_node_view(cascade, node_id)
    parts = [render_briefing(view), f"state: {node.state.name}"]

    ctx = node.context
    delivered: list[str] = []
    if ctx:
        if ctx.summary:
            delivered.append(f"  summary: {ctx.summary}")
        if ctx.provenance:
            freshness = _render_freshness_from_provenance(ctx.provenance)
            if freshness:
                delivered.append(f"  freshness: {freshness}")
        if ctx.critical:
            delivered.append(f"  critical: {json.dumps(ctx.critical, ensure_ascii=False)}")
        if ctx.artifacts:
            delivered.append(f"  artifacts:\n{_block(ctx.artifacts)}")

    if delivered:
        parts.append("")
        parts.append("[delivered by this node]")
        parts.extend(delivered)
    elif node.state.name == "COMPLETED":
        parts.append("")
        parts.append("[delivered by this node]")
        parts.append("  (no context delivered)")

    return "\n".join(parts)


def _block(text: str, prefix: str = "    |") -> str:
    """Render text as an indented block with | prefix on every line."""
    return "\n".join(prefix + line for line in text.split("\n"))


def _format_elapsed(seconds: float) -> str:
    """Format elapsed seconds as human-readable duration."""
    s = int(seconds)
    if s < 60:
        return f"{s}s ago"
    if s < 3600:
        m, sec = divmod(s, 60)
        return f"{m}m {sec}s ago" if sec else f"{m}m ago"
    if s < 86400:
        h, remainder = divmod(s, 3600)
        m = remainder // 60
        return f"{h}h {m}m ago" if m else f"{h}h ago"
    d, remainder = divmod(s, 86400)
    h = remainder // 3600
    return f"{d}d {h}h ago" if h else f"{d}d ago"


def _commits_behind(git_ref: str) -> int | None:
    """Count commits between git_ref and HEAD. Returns None on failure."""
    try:
        r = subprocess.run(
            ["git", "rev-list", "--count", f"{git_ref}..HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode == 0:
            return int(r.stdout.strip())
    except (OSError, subprocess.TimeoutExpired, ValueError):
        pass
    return None


def _freshness_parts(produced_at: float, git_ref: str) -> list[str]:
    """Build freshness parts from provenance fields."""
    parts: list[str] = []
    if produced_at:
        elapsed = time.time() - produced_at
        if elapsed >= 0:
            parts.append(_format_elapsed(elapsed))
    if git_ref:
        behind = _commits_behind(git_ref)
        if behind is not None:
            if behind == 0:
                parts.append("at HEAD")
            else:
                parts.append(f"{behind} commits behind HEAD")
    return parts


def _render_freshness_from_provenance(prov: "Provenance") -> str:
    """Render freshness from a typed Provenance object."""
    parts = _freshness_parts(prov.produced_at, prov.git_ref)
    return " | ".join(parts) if parts else ""


def _render_freshness_from_prov_dict(prov: dict[str, Any]) -> str:
    """Render freshness from a serialized provenance dict."""
    parts = _freshness_parts(float(prov.get("produced_at", 0)), str(prov.get("git_ref", "")))
    return " | ".join(parts) if parts else ""


def render_briefing(view: dict[str, Any]) -> str:
    """Render a task view as a compact briefing for LLM agents.

    Uses indentation for structure, explicit subjects for direction.
    """
    lines: list[str] = [f"Task: {view['id']}"]

    upstream = view.get("upstream", [])
    for entry in upstream:
        nid = entry["node_id"]
        dist = entry["distance"]
        label = "direct" if dist == 1 else f"distance {dist}"
        lines.append("")
        lines.append(f"[upstream: {nid}, {label}]")

        if entry.get("expectation"):
            lines.append(f"  you expected: {entry['expectation']}")
        if entry.get("promise"):
            lines.append(f"  {nid} promised: {entry['promise']}")

        delivered = entry.get("delivered", {})
        prov = delivered.get("provenance", {})
        deliverables = prov.get("deliverables", {})
        if deliverables:
            delivered_text = deliverables.get(view["id"], "")
            if delivered_text:
                lines.append(f"  {nid} delivered: {delivered_text}")

        if delivered.get("summary"):
            lines.append(f"  summary: {delivered['summary']}")
        if prov:
            freshness = _render_freshness_from_prov_dict(prov)
            if freshness:
                lines.append(f"  freshness: {freshness}")
        if delivered.get("critical"):
            lines.append(f"  critical: {json.dumps(delivered['critical'], ensure_ascii=False)}")
        if delivered.get("artifacts"):
            lines.append(f"  artifacts:\n{_block(delivered['artifacts'])}")

    promises = view.get("promises", [])
    if promises:
        lines.append("")
        lines.append("[promises]")
        for i, p in enumerate(promises):
            if i > 0:
                lines.append("")
            lines.append(f"  {p['to_node']} expects: {p['expectation']}")
            lines.append(f"  you promise: {p['promise']}")

    visible = view.get("visible_nodes", {})
    if visible:
        lines.append("")
        lines.append("[downstream]")
        for dist_key in sorted(visible.keys()):
            for n in visible[dist_key]:
                lines.append(f"  {n['id']} ({n['state']}, distance {dist_key})")

    return "\n".join(lines)


def _get_visible_descendants(
    cascade: Cascade, node_id: str, max_distance: int = 2
) -> dict[str, Any]:
    """Get visible descendant nodes within specified distance."""
    result: dict[str, Any] = {}
    visited: dict[str, int] = {node_id: 0}
    queue = deque([(node_id, 0)])

    while queue:
        current_id, distance = queue.popleft()
        if distance < max_distance:
            for dependent in cascade.get_dependents(current_id):
                if dependent.id not in visited:
                    visited[dependent.id] = distance + 1
                    queue.append((dependent.id, distance + 1))

        if distance == 0 or distance > max_distance:
            continue

        current_node = cascade.nodes[current_id]
        node_info: dict[str, Any] = {"id": current_node.id, "state": current_node.state.name}

        expectations = []
        for dep_info in cascade.get_node_dependencies_info(current_id):
            expect_info: dict[str, Any] = {"node_id": dep_info["node_id"]}
            if dep_info["expectation"]:
                expect_info["expectation"] = dep_info["expectation"]
            if dep_info["promise"]:
                expect_info["promise"] = dep_info["promise"]
            expectations.append(expect_info)
        if expectations:
            node_info["expectations"] = expectations

        distance_key = str(distance)
        if distance_key not in result:
            result[distance_key] = []
        result[distance_key].append(node_info)

    return result
