# Cascade

A cascade-based collaboration framework for multi-agent systems.

## Design Principles

- **Mandatory Contracts on Edges**: Every edge carries a `Contract(expectation, promise)` — both fields required and non-empty
- **Computed Readiness**: Node readiness is always recalculated from upstream state, never cached
- **Forward-Only Rework**: Corrective nodes are derived, never mutating completed work
- **Event Sourcing**: Append-only event log (`events.jsonl`) for audit trail and time-travel debugging
- **Critical Path Scheduling**: `get_task()` assigns the READY node on the longest downstream path first
- **Go-Style Cancellation Tokens**: Cancellation propagates through the DAG via `CancellationToken`
- **3-Tier Context Propagation**: Critical (propagates indefinitely), Summary (distance <= 2), Artifacts (always propagates)

## Installation

```bash
uv sync
```

## Quick Start

```python
from cascade import Cascade, Node, NodeState, GraphStorage

# Create storage
storage = GraphStorage(".cascade")

# Add tasks with dependencies and contracts
from tools import add_node, get_task, finish_task

add_node(storage, {
    "node_id": "analyze",
    "description": "Analyze requirements",
})
add_node(storage, {
    "node_id": "design",
    "dependencies": ["analyze"],
    "expectations": [{"node_id": "analyze",
        "expectation": "Feature list and constraints",
        "promise": "Will provide prioritized feature list"}],
})
add_node(storage, {
    "node_id": "implement",
    "dependencies": ["design"],
    "expectations": [{"node_id": "design",
        "expectation": "API specification",
        "promise": "Will provide endpoint designs"}],
})

# Get and complete a task
task = get_task(storage, {"agent_id": "agent-001"})
finish_task(storage, {
    "task_id": "analyze",
    "success": True,
    "summary": "Requirements analyzed",
    "critical": {"features": ["auth", "api"]},
})
```

## Module Structure

Dependency chain: `types -> core -> context -> view -> operations -> tools`

```
cascade/
  types.py          # Value types: Contract, Context, ContextLevel, EdgeId — no internal deps
  core/             # Cascade graph, Node, NodeState with transition rules
  context/          # Context propagation + Go-style CancellationToken
  view.py           # Presentation layer for agent task views
  operations/       # Split, Remove, Rework operations with base class
  storage/          # JSON persistence with fcntl file locking + EventStore
tools/              # LLM-facing tool functions (serialization boundary)
```

### Key Types

`Contract`, `Context`, `ContextLevel`, `Node`, `NodeState`, `EdgeId`, `CancellationToken`, `OperationResult`

## Core Concepts

### Node States

```
PENDING -> READY -> ACTIVE -> COMPLETED
                 ACTIVE -> READY (release)
                 any -> CANCELLED / FAILED
```

Readiness is **computed**, not stored. When dependencies change, `_update_readiness()` recalculates whether a node should be READY or PENDING based on whether all upstream nodes are COMPLETED.

### Contract Type

Every edge carries a mandatory `Contract(expectation, promise)`. Both fields are required and non-empty. Different downstream nodes can receive different promises from the same upstream node.

### Context Propagation

Context from completed tasks is **merged** and propagated to downstream tasks:
- `critical`: Key-value pairs, propagates indefinitely (latest wins on conflict)
- `summary`: Text summaries, propagates to grandchildren (distance <= 2)
- `artifacts`: Content strings, always propagates

### Rework Mechanism

When a downstream agent finds upstream output inadequate, it requests **rework** -- a forward-only corrective node is created (never mutate completed work). The corrective node depends on the original and feeds back into the requester, keeping the DAG acyclic.

### Event Sourcing

All graph mutations are recorded in an append-only event log (`events.jsonl`). This provides an audit trail, time-travel debugging, and replay capability.

### Critical Path Scheduling

`get_task()` uses critical-path scheduling: among READY nodes, the one on the longest path through the DAG is assigned first to minimize overall completion time.

## Tools

Tools are framework-agnostic functions that take `(GraphStorage, dict)` and return `dict`.

| Category | Tools |
|-----------|-------|
| Structure | `add_node`, `remove_node`, `split_node`, `refine_node`, `edit_node` |
| Execution | `get_task`, `finish_task` |
| Feedback | `rework` |
| Monitoring | `check_timeouts` |
| Query | `list_nodes`, `history` |

## Documentation

See [docs/usage.md](docs/usage.md) for detailed usage guide.

## License

Apache-2.0
