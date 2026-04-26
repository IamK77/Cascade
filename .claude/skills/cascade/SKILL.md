---
name: cascade
description: Multi-agent task coordination using DAG-based scheduling. Use when multiple Claude Code sessions need to collaborate on tasks with dependencies, or when managing complex multi-step workflows.
allowed-tools: Read, Edit, Write, Bash, Grep, Glob
argument-hint: [command] [options]
---

# Cascade - Multi-Agent Task Coordination

DAG-based task scheduling framework for coordinating work between multiple LLM agents.

## What Cascade Is

Cascade is an **agent factory with dynamic DAG scheduling**. The core pattern:

1. **Orchestrator** (main agent) builds and dynamically adjusts a task DAG
2. **Stateless workers** (sub-agents) claim tasks from the pipeline, execute them, deliver output, and exit
3. **Context flows** through the DAG — each worker sees upstream output when claiming a task
4. **Orchestrator monitors and adapts** — splitting tasks, triggering rework, adding dependencies, removing tasks based on runtime feedback

### Key Mental Model

The orchestrator is NOT a static planner. It:
- Monitors agent output as tasks complete
- Splits tasks that are too large (`split_node`)
- Triggers rework when output is wrong (`rework`)
- Adds dependencies discovered at runtime (`refine_node`)
- Removes tasks that become unnecessary (`remove_node`)
- Adjusts task scope mid-flight (`edit_node`)

Workers are stateless — they don't know the full DAG. They see only their upstream context and downstream promises.

### Task Splitting for Parallelism

**Maximize horizontal splitting.** Instead of a chain A → B → C, prefer splitting into parallel tasks wherever possible:

```
     A
   / | \
  B1 B2 B3    ← parallel execution
   \ | /
     C
```

More parallelism = faster completion. Split aggressively; merge at sync points.

## Two Ways to Use

### CLI (for terminal / independent processes)

```bash
cascade add-node --id analyze
cascade get-task --agent agent-001
cascade finish-task --task analyze --success --summary "Done"
```

Requires installation: `cd /path/to/Cascade && uv tool install .`

Check: !`command -v cascade >/dev/null 2>&1 && echo "✅ cascade CLI available" || echo "❌ Not installed — use Python API instead"`

### Python API (for subagents / programmatic use)

```python
from cascade import GraphStorage, add_node, get_task, finish_task

storage = GraphStorage()
add_node(storage, {"node_id": "analyze"})
get_task(storage, {"agent_id": "agent-001"})
finish_task(storage, {"task_id": "analyze", "success": True, "summary": "Done"})
```

Works from any Python environment with `uv run` — no installation needed.

### Which to use?

- **CLI**: when running as a standalone process or from shell scripts
- **Python**: when running as a subagent (Agent tool), or when CLI is not installed

Both use the same underlying tools and share the same `.cascade/` state.

## Quick Reference

| Command | Description | Details |
|---------|-------------|---------|
| `add-node` | Create a new task | [commands/add-node.md](commands/add-node.md) |
| `get-task` | Claim a task to work on | [commands/get-task.md](commands/get-task.md) |
| `finish-task` | Complete, fail, or release | [commands/finish-task.md](commands/finish-task.md) |
| `list-nodes` | View all tasks | [commands/list-nodes.md](commands/list-nodes.md) |
| `split-node` | Break into subtasks | [commands/split-node.md](commands/split-node.md) |
| `refine-node` | Add dependency | [commands/refine-node.md](commands/refine-node.md) |
| `remove-node` | Delete a task | [commands/remove-node.md](commands/remove-node.md) |
| `edit-node` | Update properties | [commands/edit-node.md](commands/edit-node.md) |
| `rework` | Request upstream correction | [commands/rework.md](commands/rework.md) |
| `check-task` | Check if task claim is still valid | [commands/check-task.md](commands/check-task.md) |
| `check-timeouts` | Release stalled tasks | [commands/check-timeouts.md](commands/check-timeouts.md) |
| `history` | Query event log | [commands/history.md](commands/history.md) |

## Common Patterns

```bash
# Create task graph (independent roots allowed)
cascade add-node --id analyze
cascade add-node --id design --deps analyze --expectations '[{"node_id": "analyze", "expectation": "Spec", "promise": "Design doc"}]'

# Work through tasks (with optional timeout)
cascade get-task --agent agent-001 --timeout 3600
cascade finish-task --task analyze --success \
  --summary "Requirements gathered" \
  --critical '{"tech": "Next.js"}'

# Request rework when upstream is wrong
cascade rework --source analyze --corrective analyze-v2 \
  --reason "Missing OAuth requirements" --agent agent-001

# Check progress
cascade list-nodes --state READY
cascade history --summary
```

## Core Concepts

- **Node States**: PENDING → READY → ACTIVE → COMPLETED/FAILED/CANCELLED
  - ACTIVE → READY (release), any non-terminal → FAILED (cascade failure)
- **Readiness**: Computed from graph structure, never cached. A node is READY when all dependencies are COMPLETED.
- **Context Flow**: summary (text, 2 hops), critical (KV, infinite), artifacts (file, infinite)
- **Contracts**: Expectation/promise on edges — your output IS your fulfilled promise
- **Critical Path**: Ready nodes are prioritized by downstream depth (most unblocking first)
- **Event Log**: Every action recorded in append-only events.jsonl

See [concepts.md](concepts.md) for detailed explanations.

## Context System

See [context.md](context.md) for when to use `critical`, `summary`, or `artifacts`.

## Error Handling

See [error-handling.md](error-handling.md) for failure scenarios and recovery.

## Complete Example

See [examples.md](examples.md) for end-to-end workflows including rework.

## Rules

1. **One task per agent** — An agent can only hold one ACTIVE task
2. **Contracts on edges** — Every edge must have expectation and promise
3. **Forward-only feedback** — Rework creates new nodes, never reverse edges
4. **Independent groups allowed** — Multiple disconnected subgraphs are fine
5. **Maximize parallelism** — Split tasks horizontally for higher concurrency
6. **Orchestrator adapts** — Monitor output and dynamically adjust the DAG; don't treat the initial plan as fixed
