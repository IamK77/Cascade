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

"""DAG visualization — mermaid and ASCII rendering.

Generates visual representations of the Cascade graph, including
node states, critical path highlighting, and contract labels.
"""

from cascade.core.cascade import Cascade
from cascade.core.state import NodeState

# Mermaid state → style mapping
_STATE_STYLES: dict[NodeState, str] = {
    NodeState.READY: "fill:#4CAF50,color:#fff",  # green
    NodeState.PENDING: "fill:#9E9E9E,color:#fff",  # gray
    NodeState.ACTIVE: "fill:#2196F3,color:#fff",  # blue
    NodeState.COMPLETED: "fill:#8BC34A,color:#fff",  # light green
    NodeState.FAILED: "fill:#F44336,color:#fff",  # red
    NodeState.CANCELLED: "fill:#FF9800,color:#fff",  # orange
}

_STATE_ICONS: dict[NodeState, str] = {
    NodeState.READY: "◻",
    NodeState.PENDING: "◌",
    NodeState.ACTIVE: "▶",
    NodeState.COMPLETED: "✓",
    NodeState.FAILED: "✗",
    NodeState.CANCELLED: "⊘",
}


def to_mermaid(
    cascade: Cascade, show_contracts: bool = False, show_critical_path: bool = True
) -> str:
    """Generate a Mermaid flowchart from the Cascade.

    Args:
        cascade: The Cascade to visualize.
        show_contracts: If True, label edges with contract expectations.
        show_critical_path: If True, highlight the critical path in bold.

    Returns:
        Mermaid diagram string (paste into any mermaid renderer).
    """
    if not cascade.nodes:
        return "graph TD\n    empty[No nodes]"

    lines = ["graph TD"]

    # Compute critical path for highlighting
    critical_set: set[str] = set()
    if show_critical_path:
        critical_set = set(cascade.get_critical_path())

    # Node definitions
    for node_id, node in cascade.nodes.items():
        icon = _STATE_ICONS.get(node.state, "?")
        label = f"{icon} {node_id}"
        if node.agent_id:
            label += f"\\n({node.agent_id})"

        # Mermaid node shape based on state
        if node.state == NodeState.ACTIVE:
            lines.append(f'    {node_id}[["{label}"]]')  # stadium shape
        elif node.state.is_terminal():
            lines.append(f'    {node_id}(["{label}"])')  # rounded
        else:
            lines.append(f'    {node_id}["{label}"]')  # rectangle

    lines.append("")

    # Edges
    for (from_id, to_id), contract in cascade.contracts.items():
        if from_id in critical_set and to_id in critical_set:
            arrow = "==>"  # thick arrow for critical path
        else:
            arrow = "-->"

        if show_contracts and contract.expectation:
            # Truncate long expectations
            label = contract.expectation[:40]
            if len(contract.expectation) > 40:
                label += "..."
            lines.append(f'    {from_id} {arrow}|"{label}"| {to_id}')
        else:
            lines.append(f"    {from_id} {arrow} {to_id}")

    lines.append("")

    # Style classes
    for node_id, node in cascade.nodes.items():
        style = _STATE_STYLES.get(node.state)
        if style:
            lines.append(f"    style {node_id} {style}")

    return "\n".join(lines)


def to_ascii(cascade: Cascade) -> str:
    """Generate a compact ASCII status view of the Cascade.

    Shows each node with its state, agent, and dependency info.
    Nodes are listed in topological order when possible.

    Example output:
        ✓ analyze          COMPLETED
        ▶ design           ACTIVE     (agent-1)
          ├── analyze ✓
        ◻ implement        READY
          ├── design ▶
        ◌ deploy           PENDING
          ├── implement ◻
    """
    if not cascade.nodes:
        return "(empty graph)"

    order = cascade.topological_sort()

    critical_set = set(cascade.get_critical_path())
    lines: list[str] = []

    for node_id in order:
        node = cascade.nodes[node_id]
        icon = _STATE_ICONS.get(node.state, "?")
        marker = " *" if node_id in critical_set else ""

        # Main line: icon + name + state + agent
        parts = [f"{icon} {node_id:<20s} {node.state.name}"]
        if node.agent_id:
            parts.append(f"({node.agent_id})")
        parts.append(marker)
        lines.append("  ".join(parts))

        # Dependency lines
        deps = cascade.get_dependencies(node_id)
        for dep in deps:
            dep_icon = _STATE_ICONS.get(dep.state, "?")
            lines.append(f"    ├── {dep.id} {dep_icon}")

    return "\n".join(lines)
