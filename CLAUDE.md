# Cascade

DAG-based multi-agent task scheduling framework.

## Commands

```bash
uv run pytest tests/        # Run all tests
uv sync                     # Install dependencies
```

## Architecture

```
types → core → context → view → operations → tools
```

Module dependencies form a verified DAG — no circular imports.

## Key Principles

- Contracts on edges, not nodes — `Contract(expectation, promise)`
- Readiness computed from graph, never cached — no `in_degree` field
- Forward-only feedback — rework derives new nodes, never reverse edges
- Independent task groups allowed — no connected graph constraint
- Append-only event log at `.cascade/events.jsonl`

## Tools (11 total)

`add_node`, `remove_node`, `split_node`, `refine_node`, `edit_node`,
`get_task`, `finish_task`, `rework`, `check_timeouts`, `list_nodes`, `history`

## Context Flow

When completing a task, use `summary` (text, 2 hops), `critical` (KV, infinite),
and `artifacts` (file, infinite) to pass output to downstream agents.

## File Layout

- `src/cascade/types.py` — shared value types (Contract, Context, EdgeId)
- `src/cascade/core/` — Cascade graph, Node, NodeState
- `src/cascade/context/` — propagation + cancellation
- `src/cascade/view.py` — agent task view builder
- `src/cascade/events.py` — event store
- `src/cascade/operations/` — Split, Remove, Rework
- `src/cascade/storage/` — JSON persistence + file locking
- `src/tools/` — LLM-facing tool functions
