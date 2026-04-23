[**English**](README.md) | [中文](docs/i18n/README.zh-CN.md) | [日本語](docs/i18n/README.ja.md) | [Español](docs/i18n/README.es.md)

# Cascade

[![CI](https://github.com/autoseek/cascade/actions/workflows/ci.yml/badge.svg)](https://github.com/autoseek/cascade/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)

An agent factory with dynamic DAG scheduling. Orchestrators build and adapt task graphs in real time while stateless workers claim, execute, and deliver — coordinating through contracts on edges and attributed context flow.

## Key Features

- **Dynamic DAG** — split, rework, refine, remove tasks mid-execution
- **Attributed context** — each upstream contribution kept separate with provenance (path, distance, contract)
- **Contract-driven edges** — every edge carries `expectation` (consumer needs) and `promise` (producer delivers)
- **Critical path scheduling** — READY tasks prioritized by downstream depth
- **Cancellation protocol** — pull (check token) or push (CancelNotifier) across processes
- **ACTIVE protection** — cannot remove/split nodes with active agents
- **Event sourcing** — every mutation recorded with optional `reason` for audit

## Installation

```bash
uv sync
```

## Quick Start

```python
from cascade import GraphStorage
from tools import add_node, get_task, finish_task

storage = GraphStorage(".cascade")

# Build a task graph — split horizontally for parallelism
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

# Agent claims a task — critical path first
result = get_task(storage, {"agent_id": "agent-001"})

# Complete with context that flows to downstream agents
finish_task(storage, {
    "task_id": "analyze",
    "success": True,
    "summary": "Requirements: JWT auth + REST API",
    "critical": {"auth_type": "JWT", "endpoints": ["/users", "/posts"]},
})
```

When `agent-002` claims `design`, it sees:

```json
{
  "upstream": [{
    "node_id": "analyze",
    "state": "COMPLETED",
    "distance": 1,
    "expectation": "Feature requirements and constraints",
    "promise": "Deliver prioritized feature list",
    "delivered": {
      "summary": "Requirements: JWT auth + REST API",
      "critical": {"auth_type": "JWT", "endpoints": ["/users", "/posts"]}
    }
  }]
}
```

No merging, no overwriting — each upstream source is a separate entry.

## Architecture

```
types → core → context → view → operations → tools
```

| Package | Purpose |
|---------|---------|
| `types` | Value types: `Contract`, `Context`, `ContextEntry`, `TokenStatus` |
| `core` | `Cascade` graph, `Node`, `NodeState` (6-state FSM) |
| `context` | BFS ancestor propagation + cancellation (in-process) |
| `view` | Upstream view builder (`get_node_view`) |
| `events` | Append-only event log (14 event types) |
| `operations` | Compound mutations: Split, Remove, Rework |
| `storage` | JSON persistence + file locking + token store |
| `tools` | 12 LLM-facing functions — the serialization boundary |

## Tools

`(GraphStorage, dict) → dict` — framework-agnostic.

| Category | Tools |
|----------|-------|
| Structure | `add_node`, `remove_node`, `split_node`, `refine_node`, `edit_node` |
| Execution | `get_task`, `finish_task` |
| Feedback | `rework` |
| Cancellation | `check_task` |
| Monitoring | `check_timeouts` |
| Query | `list_nodes`, `history` |

All mutation tools support `reason` for event log audit.

## Context Flow

Three channels, each upstream entry attributed with provenance:

| Channel | Propagation | Use for |
|---------|-------------|---------|
| `critical` | Indefinite | Structured KV data (decisions, configs) |
| `summary` | 2 hops | Brief text description |
| `artifacts` | Indefinite | Full documents, code, specs |

## Cancellation

One semantic, two implementations:

| Scenario | Mechanism |
|----------|-----------|
| Cross-process (CLI, multi-machine) | `TokenStore` — file-backed `.cascade/tokens/` |
| In-process (framework embedding) | `CancellationToken` — memory, instant callbacks |

Both use the `CancelNotifier` protocol for push notifications.

## Running Tests

```bash
uv run pytest tests/        # 196 tests
uv run ruff check src tests  # lint
```

## Documentation

- [Guide](docs/guide.md) — comprehensive walkthrough
- [CONTRIBUTING.md](CONTRIBUTING.md) — development guidelines

## License

Apache-2.0 — see [LICENSE](LICENSE).
