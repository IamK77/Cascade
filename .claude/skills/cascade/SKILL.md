---
name: cascade
description: Multi-agent task coordination using DAG-based scheduling. Use when multiple Claude Code sessions need to collaborate on tasks with dependencies, or when managing complex multi-step workflows.
allowed-tools: Read Edit Write Bash Grep Glob
---

# Cascade

It's a pleasure to have you orchestrate multi-agent work. The DAG you build is the contract workers depend on — pursue **self-consistent elegance**, build for production, and reject patches or minimal-effort shortcuts. When the design is right, watching parallel workers deliver in clean waves is genuinely satisfying; that satisfaction is the signal you got it right.

## Roles

| Role | Responsibility | Constraint |
|------|---------------|------------|
| **Orchestrator** | Build the DAG, dispatch workers, adapt the graph | Never claim or execute tasks — you are the architect, not a laborer |
| **Worker** | Claim one task, do the work, finish | One ACTIVE task per agent — finish before claiming another |

Why the separation: if the orchestrator claims tasks, it blocks on execution and cannot react to other workers' completions, stalls, or failures. The DAG loses its coordinator.

## Rules

1. **Contracts on edges** — every dependency carries `expectation` (consumer's need) + `promise` (upstream's deliverable). Why: without explicit contracts, downstream agents hallucinate what upstream delivered. Contracts are the single source of truth for information needs.

2. **Forward-only feedback** — rework derives new corrective nodes, never reverses edges. Why: reversing edges creates cycles, breaks topological ordering, and invalidates work already done by downstream agents. The DAG grows forward, always.

3. **ACTIVE protection** — cannot remove/split nodes with active agents. Why: an agent is mid-execution; mutating its node would invalidate its work silently. Release or wait for completion first.

4. **Parallelism** — multiple `Agent()` calls in one message run concurrently. The initial DAG is a hypothesis — adapt it as reality reveals itself.

## Workflow

```
1. Build initial DAG (add-nodes)
2. Dispatch workers for READY tasks (Agent calls)
3. Monitor via `cascade watch` — react to transitions
   ├─ COMPLETED → inspect output, dispatch next wave
   ├─ FAILED → diagnose, rework or remove
   └─ Stalled (no transition for too long) → check-timeouts
4. Adapt the DAG (see Adapt table below)
5. Repeat until all nodes COMPLETED
```

## Adapt

When workers complete or fail, branch on what you observe:

| Signal | Operation | When to read |
|--------|-----------|--------------|
| Task too large, or peer took 3x longer | `split-node` | [references/split-node.md](references/split-node.md) |
| Upstream output wrong or incomplete | `rework` | [references/rework.md](references/rework.md) |
| Hidden dependency discovered mid-work | `refine-node` | [references/refine-node.md](references/refine-node.md) |
| Task no longer needed | `remove-node` | [references/remove-node.md](references/remove-node.md) |
| Scope change on existing task | `edit-node` | [references/edit-node.md](references/edit-node.md) |
| Agent stalled (no progress) | `check-timeouts` | [references/check-timeouts.md](references/check-timeouts.md) |

## When Things Go Wrong

| Failure | Recovery |
|---------|----------|
| Worker returns `ALREADY_HAS_ACTIVE` | That agent didn't finish its previous task. Send it `finish-task --release` first |
| Worker returns `TASK_NOT_READY` | Dependencies not met. Check `list-nodes --state PENDING` — something upstream is blocked |
| Worker returns `LOCK_CONTENTION` | Another process holds the lock. Wait and retry (framework retries 3x automatically) |
| Worker completes but output is wrong | Use `rework` — do NOT edit the completed node's context directly |
| Worker stalls (no finish after timeout) | Run `check-timeouts`; inspect the released task, then re-dispatch or split |
| Graph feels stuck (nothing READY) | `list-nodes` — look for cycles of PENDING or forgotten ACTIVE tasks |

## Installation

```bash
pipx install cascade-auto
```

!`command -v cascade >/dev/null 2>&1 && cascade --help 2>&1 || echo "cascade not installed — run: pipx install cascade-auto"`

## Commands

Read the reference for a command when you need its exact parameters or output format:

| When you need to... | Read |
|---------------------|------|
| Build the initial DAG | [add-node.md](references/add-node.md), [add-nodes.md](references/add-nodes.md) |
| Dispatch a worker or understand what it sees | [get-task.md](references/get-task.md) |
| Understand completion/failure/release | [finish-task.md](references/finish-task.md) |
| Monitor graph state | [list-nodes.md](references/list-nodes.md), [history.md](references/history.md) |
| Inspect a node without claiming | [inspect.md](references/inspect.md) |
| Stream transitions in real-time | [watch.md](references/watch.md) |

For the context system, sub-agent prompt templates, and orchestrator loop: [references/concepts.md](references/concepts.md)

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
