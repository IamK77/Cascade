---
name: cascade
description: Multi-agent task coordination using DAG-based scheduling. Use when multiple Claude Code sessions need to collaborate on tasks with dependencies, or when managing complex multi-step workflows.
allowed-tools: Read, Edit, Write, Bash, Grep, Glob
argument-hint: [command] [options]
---

# Cascade

It's a pleasure to have you orchestrate multi-agent work. The DAG you build is the contract workers depend on — pursue **self-consistent elegance**, build for production, and reject patches or minimal-effort shortcuts. When the design is right, watching parallel workers deliver in clean waves is genuinely satisfying; that satisfaction is the signal you got it right.

1. **You are the orchestrator** — build the DAG, dispatch workers, adapt the plan. You never claim or execute tasks
2. **Spawn workers in parallel** — multiple Agent() calls in one message = concurrent execution
3. **Workers claim one task** via `cascade get-task`, do the work, call `cascade finish-task`
4. **Context flows automatically** — workers see upstream output without extra wiring

## Installation

```bash
pipx install cascade-auto
```

!`command -v cascade >/dev/null 2>&1 && cascade --help 2>&1 || echo "cascade not installed — run: pipx install cascade-auto"`

## Commands

See `commands/<name>.md` for: add-node, get-task, finish-task, list-nodes, split-node, refine-node, remove-node, edit-node, rework, check-task, check-timeouts, history, inspect.

## Common Patterns

```bash
# Build DAG
cascade add-node --id analyze
cascade add-node --id design --deps analyze \
  --expectations '[{"node_id": "analyze", "expectation": "Spec", "promise": "Design doc"}]'

# Worker claims and completes
cascade get-task --agent worker-1 --task analyze
cascade finish-task --task analyze --success \
  --summary "Requirements gathered" \
  --critical '{"tech": "Next.js"}'

# Dynamic adjustments
cascade split-node --parent implement --children impl-auth,impl-api --reason "Too large"
cascade rework --source analyze --corrective analyze-v2 \
  --reason "Missing OAuth requirements" --agent agent-001 \
  --source-expectation "Original spec" --source-promise "First analysis" \
  --corrective-expectation "Revised spec with OAuth" --corrective-promise "Updated requirements"
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
