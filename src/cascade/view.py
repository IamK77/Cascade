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
from collections import deque
from typing import Any

from cascade.context.propagator import ContextPropagator
from cascade.core.cascade import Cascade
from cascade.types import DeliveredContext, UpstreamEntry


def get_node_view(cascade: Cascade, node_id: str) -> dict[str, Any]:
    """Get all information an agent needs to execute a node.

    Composes data from multiple sources:
    - upstream: each ancestor with contract (if direct) and delivered context
    - promises: what this node owes to downstream dependents
    - visible_nodes: downstream topology (2 hops)
    """
    if node_id not in cascade.nodes:
        raise ValueError(f"Node {node_id} not found")

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
        return f"# Task: {node_id} (not found)"

    node = cascade.nodes[node_id]
    view = get_node_view(cascade, node_id)
    parts = [render_briefing(view), f"_State: {node.state.name}_", ""]

    ctx = getattr(node, "context", None)
    delivered: list[str] = []
    if ctx:
        if getattr(ctx, "summary", ""):
            delivered.append(f"- **Summary**: {ctx.summary}")
        if getattr(ctx, "critical", None):
            delivered.append("- **Critical**:")
            delivered.append("  ```json")
            delivered.append(f"  {json.dumps(ctx.critical, indent=2, ensure_ascii=False)}")
            delivered.append("  ```")
        if getattr(ctx, "artifacts", ""):
            delivered.append(f"- **Artifacts**: {ctx.artifacts}")

    if delivered:
        parts.append("## Delivered (this node's output)")
        parts.append("")
        parts.extend(delivered)
        parts.append("")
    elif node.state.name == "COMPLETED":
        parts.append("## Delivered (this node's output)")
        parts.append("")
        parts.append("_No context delivered — node completed without summary/critical/artifacts._")
        parts.append("")

    return "\n".join(parts)


def render_briefing(view: dict[str, Any]) -> str:
    """Render a task view as a markdown briefing.

    Pure factual statements — no behavioral instructions.
    """
    lines: list[str] = []
    lines.append(f"# Task: {view['id']}")
    lines.append("")

    upstream = view.get("upstream", [])
    if upstream:
        lines.append("## Upstream Context")
        lines.append("")
        for entry in upstream:
            nid = entry["node_id"]
            dist = entry["distance"]
            label = "direct dependency" if dist == 1 else f"ancestor, distance {dist}"
            lines.append(f"### {nid} ({label})")
            lines.append("")

            if entry.get("expectation"):
                lines.append(f"- **Expects from you**: {entry['expectation']}")
            if entry.get("promise"):
                lines.append(f"- **Promised to deliver**: {entry['promise']}")

            delivered = entry.get("delivered", {})
            if delivered.get("summary"):
                lines.append(f"- **Summary**: {delivered['summary']}")
            if delivered.get("critical"):
                lines.append("- **Critical data**:")
                lines.append("  ```json")
                lines.append(f"  {json.dumps(delivered['critical'], indent=2, ensure_ascii=False)}")
                lines.append("  ```")
            if delivered.get("artifacts"):
                lines.append(f"- **Artifacts**: {delivered['artifacts']}")

            lines.append("")

    promises = view.get("promises", [])
    if promises:
        lines.append("## Promises to Downstream")
        lines.append("")
        for p in promises:
            lines.append(f"- → **{p['to_node']}**: {p['promise']}")
        lines.append("")

    visible = view.get("visible_nodes", {})
    if visible:
        lines.append("## Downstream Topology")
        lines.append("")
        for dist_key in sorted(visible.keys()):
            nodes = visible[dist_key]
            for n in nodes:
                lines.append(f"- {n['id']} ({n['state']}, distance {dist_key})")
        lines.append("")

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
