[**English**](README.md) | [中文](README.zh-CN.md) | [日本語](README.ja.md) | [Español](README.es.md)

# Cascade

A DAG-based multi-agent task scheduling framework. Agents claim tasks from a dependency graph, pass context through edge contracts, and coordinate via shared file state. The graph can be dynamically edited mid-execution — split, refine, rework — while maintaining consistency.

## Installation

```bash
uv sync
```

## Quick Start

```python
from cascade import GraphStorage
from tools import add_node, get_task, finish_task

storage = GraphStorage(".cascade")

# Build a task graph with contracts on edges
add_node(storage, {"node_id": "analyze"})
add_node(storage, {
    "node_id": "design",
    "dependencies": ["analyze"],
    "expectations": [{
        "node_id": "analyze",
        "expectation": "Feature requirements and constraints",
        "promise": "Deliver prioritized feature list",
    }],
})

# Agent claims a task — prioritized by critical path
task = get_task(storage, {"agent_id": "agent-001"})

# Complete with context that flows to downstream agents
finish_task(storage, {
    "task_id": "analyze",
    "success": True,
    "summary": "Requirements analyzed: auth + REST API",
    "critical": {"auth_type": "JWT", "endpoints": ["/users", "/posts"]},
})
```

## Design Principles

- **Contracts on edges** — every edge carries `Contract(expectation, promise)`, both required. Different downstream nodes can receive different promises from the same upstream node.
- **Computed readiness** — no cached `in_degree`. A node is READY when all its dependencies are COMPLETED, derived from the graph in real time.
- **Forward-only feedback** — rework creates corrective nodes that grow the graph forward. Never mutate completed work, never create reverse edges.
- **Critical path scheduling** — `get_task` assigns the READY node with the deepest downstream chain first, minimizing total completion time.
- **Event sourcing** — every mutation recorded in append-only `events.jsonl`. Audit trail, time-travel, replay.
- **3-tier context propagation** — `critical` (KV, infinite), `summary` (text, 2 hops), `artifacts` (file ref, infinite).

## Module Structure

Dependency chain (verified acyclic by topological sort):

```
types → core → context → view → operations → tools
```

| Package | Purpose |
|---------|---------|
| `types` | Value types: `Contract`, `Context`, `EdgeId`, `ContextLevel` — zero internal deps |
| `core` | `Cascade` graph, `Node`, `NodeState` with transition rules |
| `context` | Context propagation + Go-style `CancellationToken` |
| `view` | Agent-facing presentation layer (`get_node_view`) |
| `events` | Append-only event log (`EventStore`) |
| `operations` | Compound mutations: `SplitOperation`, `RemoveOperation`, `ReworkOperation` |
| `storage` | JSON persistence with `fcntl` file locking |
| `tools` | LLM-facing interface — the serialization boundary |

## Node States

```
PENDING → READY → ACTIVE → COMPLETED
                    ↕ release      ↘ FAILED
                                   ↘ CANCELLED
```

## Tools

Framework-agnostic functions: `(GraphStorage, dict) → dict`.

| Category | Tools | Description |
|----------|-------|-------------|
| Structure | `add_node` | Create a task node |
| | `remove_node` | Delete a node (optional cascade) |
| | `split_node` | Break a task into subtasks |
| | `refine_node` | Add a dependency to an existing node |
| | `edit_node` | Update state or context |
| Execution | `get_task` | Claim a task (critical path priority) |
| | `finish_task` | Complete / fail / release a task |
| Feedback | `rework` | Request upstream correction (forward-only) |
| Monitoring | `check_timeouts` | Release stalled tasks |
| Query | `list_nodes` | View all tasks and states |
| | `history` | Query event log |

## Running Tests

```bash
uv run pytest tests/
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines.

## License

Apache-2.0 — see [LICENSE](LICENSE) for details.
