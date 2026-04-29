---
name: cascade
description: Multi-agent task coordination using DAG-based scheduling. Use when multiple Claude Code sessions need to collaborate on tasks with dependencies, or when managing complex multi-step workflows.
allowed-tools: Read, Edit, Write, Bash, Grep, Glob
argument-hint: [command] [options]
---

# Cascade

It's a pleasure to have you orchestrate multi-agent work. The DAG you build is the contract workers depend on — pursue **self-consistent elegance**, build for production, and reject patches or minimal-effort shortcuts. When the design is right, watching parallel workers deliver in clean waves is genuinely satisfying; that satisfaction is the signal you got it right.

## Rules

1. **Orchestrator** — build the DAG, dispatch workers, adapt. Never claim or execute tasks
2. **Workers** — claim one task via `cascade get-task`, do the work, call `cascade finish-task`. One ACTIVE task per agent
3. **Contracts on edges** — every dependency carries `expectation` (consumer's need) + `promise` (upstream's deliverable)
4. **Forward-only feedback** — rework derives new nodes, never reverse edges
5. **ACTIVE protection** — cannot remove/split nodes with active agents
6. **Parallelism** — multiple Agent() calls in one message run concurrently; the DAG is a hypothesis, not a fixed plan

## Adapt

When workers complete, branch on what you observe:

| Signal | Operation |
|--------|-----------|
| Task too large, or peer took 3x longer | `split-node` |
| Upstream output wrong | `rework` |
| Hidden dependency discovered | `refine-node` |
| Task no longer needed | `remove-node` |
| Scope change | `edit-node` |
| Agent stalled | `check-timeouts` |

## Installation

```bash
pipx install cascade-auto
```

!`command -v cascade >/dev/null 2>&1 && cascade --help 2>&1 || echo "cascade not installed — run: pipx install cascade-auto"`

## Commands

See `commands/<name>.md` for: add-node, add-nodes, get-task, finish-task, list-nodes, split-node, refine-node, remove-node, edit-node, rework, check-task, check-timeouts, history, inspect, watch.

## Common Patterns

```bash
# Build DAG (one-shot, atomic — preferred for multi-node DAGs)
cascade add-nodes --json '[
  {"id": "analyze"},
  {"id": "design", "deps": ["analyze"],
   "expectations": [{"node_id": "analyze", "expectation": "Spec", "promise": "Design doc"}]}
]'

# Or single-node form
cascade add-node --id analyze

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

See [concepts.md](concepts.md) for context system, sub-agent prompts, and error recovery.
