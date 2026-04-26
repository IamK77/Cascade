# Cascade

DAG-based multi-agent task scheduling framework — an agent factory with dynamic DAG control.

Two APIs:
- **`CascadeClient`** — typed Python API with IDE support (`from cascade import CascadeClient, Contract`)
- **CLI** — shell/agent interface (`cascade add-node`, `cascade get-task`, etc.)

The underlying `(GraphStorage, dict) -> dict` tool layer is the internal serialization boundary used by both.

## Commands

```bash
uv run pytest tests/        # Run all tests
uv sync                     # Install dependencies
```

## Architecture

```
types → core → context → view → operations → tools → client
```

Module dependencies form a verified DAG — no circular imports.

## Key Principles

- Contracts on edges, not nodes — `Contract(expectation, promise)`
- Readiness computed from graph, never cached — no `in_degree` field
- Forward-only feedback — rework derives new nodes, never reverse edges
- Independent task groups allowed — no connected graph constraint
- Append-only event log at `.cascade/events.jsonl`
- ACTIVE nodes protected — cannot remove/split without release
- Maximize horizontal splitting for parallelism

## Tools (12 total)

`add_node`, `remove_node`, `split_node`, `refine_node`, `edit_node`,
`get_task`, `finish_task`, `check_task`, `rework`, `check_timeouts`, `list_nodes`, `history`

All mutation tools support `reason` parameter for event log audit trail.

## Context Flow

Upstream view: each ancestor's context is kept separate with provenance.
- `summary` (text, 2 hops) + `critical` (KV, infinite) + `artifacts` (file, infinite)
- Direct parents (distance 1): include contract (expectation/promise)
- Further ancestors: include path + distance, no contract
- Fan-in: no key overwrite — each source is a separate entry

## Cancellation

Two implementations of the same semantic — task cancellation:
- **In-process**: `CancellationToken` (memory, instant callbacks)
- **Cross-process**: `TokenStore` (file-backed `.cascade/tokens/`)
- Both use `CancelNotifier` protocol for push notifications
- Pull: `check_task` tool or `TokenStore.check()`
- Push: `FileNotifier`, `CallbackNotifier`, or custom adapter

## File Layout

- `src/cascade/types.py` — shared value types (Contract, Context, ContextEntry, TokenStatus)
- `src/cascade/core/` — Cascade graph, Node, NodeState
- `src/cascade/context/` — propagator (BFS ancestor traversal) + cancellation token
- `src/cascade/view.py` — upstream view builder (get_node_view)
- `src/cascade/events.py` — event store (14 event types)
- `src/cascade/operations/` — Split, Remove, Rework
- `src/cascade/storage/` — JSON persistence + file locking + token store
- `src/cascade/client.py` — `CascadeClient` typed Python API (wraps tools)
- `src/tools/` — LLM-facing tool functions (12 tools, dict-based internal layer)
