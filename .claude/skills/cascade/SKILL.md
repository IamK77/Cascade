---
name: cascade
description: Multi-agent task coordination using DAG-based scheduling. Use when multiple Claude Code sessions need to collaborate on tasks with dependencies, or when managing complex multi-step workflows.
allowed-tools: Read, Edit, Write, Bash, Grep, Glob
argument-hint: [command] [options]
---

# Cascade

An agent factory with dynamic DAG scheduling.

1. **You are the orchestrator** — build a task DAG, complete the root analysis yourself
2. **Spawn sub-agents for parallel tasks** — multiple Agent() calls in one message = concurrent execution
3. **Each sub-agent claims one task** via `cascade get-task`, does the work, calls `cascade finish-task`
4. **Context flows automatically** — workers see upstream output without extra wiring
5. **You monitor and adapt** — split, rework, refine, remove based on worker output

## Installation

```bash
pipx install cascade-auto
```

!`command -v cascade >/dev/null 2>&1 && cascade --help 2>&1 || echo "cascade not installed — run: pipx install cascade-auto"`

## Commands

| Command | Details |
|---------|---------|
| `add-node` | [commands/add-node.md](commands/add-node.md) |
| `get-task` | [commands/get-task.md](commands/get-task.md) |
| `finish-task` | [commands/finish-task.md](commands/finish-task.md) |
| `list-nodes` | [commands/list-nodes.md](commands/list-nodes.md) |
| `split-node` | [commands/split-node.md](commands/split-node.md) |
| `refine-node` | [commands/refine-node.md](commands/refine-node.md) |
| `remove-node` | [commands/remove-node.md](commands/remove-node.md) |
| `edit-node` | [commands/edit-node.md](commands/edit-node.md) |
| `rework` | [commands/rework.md](commands/rework.md) |
| `check-task` | [commands/check-task.md](commands/check-task.md) |
| `check-timeouts` | [commands/check-timeouts.md](commands/check-timeouts.md) |
| `history` | [commands/history.md](commands/history.md) |

## Common Patterns

```bash
# Build DAG
cascade add-node --id analyze
cascade add-node --id design --deps analyze \
  --expectations '[{"node_id": "analyze", "expectation": "Spec", "promise": "Design doc"}]'

# Claim and complete
cascade get-task --agent orchestrator --task analyze
cascade finish-task --task analyze --success \
  --summary "Requirements gathered" \
  --critical '{"tech": "Next.js"}'

# Dynamic adjustments
cascade split-node --parent implement --children impl-auth,impl-api --reason "Too large"
cascade rework --source analyze --corrective analyze-v2 \
  --reason "Missing OAuth requirements" --agent agent-001
cascade remove-node --node deprecated-task --reason "No longer needed"

# Monitor
cascade list-nodes --state READY
cascade history --summary
```

## Rules

1. **One task per agent** — an agent can only hold one ACTIVE task
2. **Contracts on edges** — every edge must have expectation and promise
3. **Forward-only feedback** — rework creates new nodes, never reverse edges
4. **Maximize parallelism** — split tasks horizontally for higher concurrency
5. **Orchestrator adapts** — the initial DAG is a hypothesis, not a fixed plan
6. **ACTIVE protection** — cannot remove/split nodes with active agents

See [concepts.md](concepts.md) for context system, orchestrator guide, and error recovery.
