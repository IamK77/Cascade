# Cascade

Multi-agent task scheduling framework using DAG-based coordination with contracts on edges.

## Running Tests

```
uv run pytest tests/
```

## Module Structure

Modules follow a strict acyclic dependency order (verified by topological sort):

1. **types** (`cascade/types.py`) — Value types: `Contract`, `Context`, `ContextLevel`, `EdgeId`. No internal imports.
2. **core** (`cascade/core/`) — Graph primitives: `Node`, `NodeState`, `Cascade` (the DAG engine). Depends only on types.
3. **context** (`cascade/context/`) — Context propagation (`ContextPropagator`), cancellation logic. Depends on core + types.
4. **view** (`cascade/view.py`) — Presentation layer: builds the dict an LLM agent receives when claiming a task. Depends on context + core.
5. **operations** (`cascade/operations/`) — Compound mutations: `SplitOperation`, `RemoveOperation`, `ReworkOperation`. Depends on core + types.
6. **tools** (`tools/`) — LLM-facing tool functions. Each takes `(GraphStorage, dict)` and returns `dict`. Depends on everything above.

Supporting modules: `cascade/events.py` (event sourcing), `cascade/storage/` (JSON persistence), `cascade/viz.py` (visualization).

## Architecture Principles

- **Contracts on edges**: Every directed edge carries a `Contract(expectation, promise)` — natural language strings describing what the dependent expects and what the dependency promises. Both fields are mandatory.
- **No redundant state**: Readiness (PENDING vs READY) is always computed from the graph, never stored or cached. `pending_dependency_count()` derives state from live edge data.
- **Forward-only feedback**: Rework creates a new corrective node with a forward edge to the original dependent. Edges never reverse direction.
- **Acyclic module dependencies**: The module layering above is enforced; adding a cycle triggers a `ValueError` from `topological_sort()`.
- **Append-only event log**: All mutations are recorded in `.cascade/events.jsonl`. Supports audit trail, time travel, and replay debugging.

## Tool Inventory

| Tool | Description |
|------|-------------|
| `add_node` | Add a new node (and optional edges) to the DAG |
| `remove_node` | Remove a node and cascade-delete its edges |
| `split_node` | Split a node into multiple new sub-nodes |
| `refine_node` | Add a new dependency to an existing node |
| `edit_node` | Edit a node's metadata (label, context, timeout) |
| `get_task` | Claim the highest-priority READY task for an agent |
| `finish_task` | Mark an ACTIVE task as completed or failed |
| `rework` | Request corrective work when upstream output is inadequate |
| `check_timeouts` | Scan ACTIVE tasks and release timed-out ones |
| `list_nodes` | List all nodes with state and dependency info |
| `history` | Query the append-only event log |

## Key Files

- `src/cascade/core/cascade.py` — Core DAG engine with cycle detection and critical-path scheduling
- `src/cascade/types.py` — All shared value types (import this, not internal modules)
- `src/cascade/events.py` — Event sourcing with `EventStore`
- `src/cascade/storage/graph_storage.py` — JSON persistence with file locking
- `src/tools/__init__.py` — Tool registry and `execute_tool()` dispatcher
