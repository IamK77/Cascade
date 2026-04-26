---
name: cascade
description: Multi-agent task coordination using DAG-based scheduling. Use when multiple Claude Code sessions need to collaborate on tasks with dependencies, or when managing complex multi-step workflows.
allowed-tools: Read, Edit, Write, Bash, Grep, Glob
argument-hint: [command] [options]
---

# Cascade - Multi-Agent Task Coordination

An agent factory with dynamic DAG scheduling for coordinating work between multiple agents.

## What Cascade Is

Cascade is an **agent factory with dynamic DAG scheduling**. Use the Agent tool to run workers in parallel.

1. **You are the orchestrator** — build a task DAG, complete the root analysis yourself
2. **Spawn sub-agents for parallel tasks** — multiple Agent() calls in one message = concurrent execution
3. **Each sub-agent claims one task** via `cascade get-task`, does the work, calls `cascade finish-task`
4. **Context flows automatically** — workers see upstream output without extra wiring
5. **You monitor and adapt** — split, rework, refine, remove based on worker output

The initial DAG is a hypothesis. Adapt it as agents deliver output.

### Task Splitting for Parallelism

**Maximize horizontal splitting.** Prefer parallel over serial:

```
     A
   / | \
  B1 B2 B3    ← parallel execution
   \ | /
     C
```

## Installation

```bash
# Install as CLI tool
pipx install cascade-auto
# or
uv tool install cascade-auto
```

Verify: !`command -v cascade >/dev/null 2>&1 && echo "✅ cascade CLI available" || echo "❌ Not installed — run: pipx install cascade-auto"`

## Commands

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
cascade add-node --id design --deps analyze \
  --expectations '[{"node_id": "analyze", "expectation": "Spec", "promise": "Design doc"}]'

# Claim and complete tasks
cascade get-task --agent agent-001 --timeout 3600
cascade finish-task --task analyze --success \
  --summary "Requirements gathered" \
  --critical '{"tech": "Next.js"}'

# Dynamic adjustments
cascade split-node --parent implement --children impl-auth,impl-api --reason "Too large"
cascade refine-node --node impl-api --dep design-schema \
  --expectation "DB schema" --promise "Schema migrations" --reason "Hidden dependency"
cascade rework --source analyze --corrective analyze-v2 \
  --reason "Missing OAuth requirements" --agent agent-001
cascade remove-node --node deprecated-task --reason "No longer needed"
cascade edit-node --node impl-auth --summary "Scope reduced" --reason "Only OAuth needed"

# Monitor progress
cascade list-nodes --state READY
cascade history --summary
cascade check-task --task analyze
```

## Core Concepts

- **Node States**: PENDING → READY → ACTIVE → COMPLETED/FAILED/CANCELLED
- **Readiness**: A node is READY when all dependencies are COMPLETED (computed, never cached)
- **Contracts**: Every edge carries `expectation` (what consumer needs) and `promise` (what producer delivers)
- **Context**: `summary` (text, 2 hops), `critical` (KV, infinite), `artifacts` (file, infinite)
- **Upstream View**: When claiming a task, each ancestor's output is a separate entry with provenance (node_id, distance, path)
- **Critical Path**: READY tasks are prioritized by downstream depth (most unblocking first)
- **ACTIVE Protection**: Cannot remove/split nodes with active agents — release first
- **Event Log**: Every mutation recorded in events.jsonl with optional `reason`

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
6. **Orchestrator adapts** — Monitor output and dynamically adjust the DAG
