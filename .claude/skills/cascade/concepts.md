# Concepts

## Node States

| State | Meaning |
|-------|---------|
| PENDING | Has uncompleted dependencies |
| READY | All dependencies completed, can be claimed |
| ACTIVE | Being worked on by an agent |
| COMPLETED | Successfully finished |
| FAILED | Failed (possibly cascaded from upstream) |
| CANCELLED | Cancelled (possibly cascaded from upstream) |

Readiness is computed from the graph, never cached. A node is READY when all its dependencies are COMPLETED.

## Context System

When a worker claims a task via `cascade get-task`, it receives an **upstream** list — each ancestor's output as a separate entry:

```json
{
  "upstream": [
    {
      "node_id": "analyze",
      "state": "COMPLETED",
      "distance": 1,
      "path": ["analyze"],
      "expectation": "Need tech stack decisions",
      "promise": "Deliver requirements spec",
      "delivered": {
        "summary": "JWT auth + REST API",
        "critical": {"auth": "JWT", "db": "PostgreSQL"}
      }
    },
    {
      "node_id": "root",
      "state": "COMPLETED",
      "distance": 2,
      "path": ["root", "analyze"],
      "delivered": {
        "critical": {"project": "e-commerce"}
      }
    }
  ]
}
```

- **distance 1** (direct parents): includes expectation/promise from the edge contract
- **distance 2+** (ancestors): includes path for provenance, no contract
- Fan-in: each source is separate — no key overwrite

Three channels — **use all three**, they serve different purposes:

| Channel | Propagation | What to put | Example |
|---------|-------------|-------------|---------|
| `summary` | **2 hops only** | Text: what was accomplished | `"Designed 5 REST endpoints with JWT auth"` |
| `critical` | **All descendants** | Structured KV that downstream tasks need to make decisions | `{"endpoints": ["/users", "/auth"], "db": "PostgreSQL"}` |
| `artifacts` | **All descendants** | Full documents, specs, code — the complete deliverable | `"# API Spec\n## POST /auth/login\n..."` |

**Only `summary` has a distance limit.** Both `critical` and `artifacts` propagate to every descendant regardless of depth. If you put interface definitions in `critical` at the analyze node, a worker 3 hops away still sees them.

**Verify what workers see:** Run `cascade get-task --agent test --task <id>` to preview the briefing a worker receives. If critical data is missing, it was never written upstream — not lost in propagation.

**Why this matters for agent speed:** Workers get context from `cascade get-task`, not from the Agent prompt. If the orchestrator puts detailed specs in `critical` and `artifacts`, workers start fast (minimal prompt) and get full context from Cascade. If the orchestrator copies context into the Agent prompt instead, startup is slower and Cascade's context system is bypassed.

## Contracts

Every edge carries `expectation` (what consumer needs) and `promise` (what producer delivers).

```
auth (upstream)
  │  promise: "Provide JWT tokens"        ← auth's commitment
  │  expectation: "Need auth for API"     ← api's requirement
  ↓
api (downstream)
```

**Promise describes what the UPSTREAM delivers, not what the downstream produces.** Common mistake: writing the promise from the downstream's perspective ("Will provide CLI wiring" on an edge TO the CLI node). The promise should describe what the edge's source node delivers ("Provide project CRUD functions"). The framework warns on duplicate promises.

## Rework

Forward-only: create a corrective node, never reverse edges.

```
Before:  A(COMPLETED) → B(ACTIVE, discovers problem)
After:   A(COMPLETED) → A'(READY) → B(PENDING, waits for A')
```

## Error Recovery

```bash
# Release — give up temporarily, task returns to READY
cascade finish-task --task X --release --reason "Blocked on external"

# Fail — task cannot be completed
cascade finish-task --task X --fail --reason "Error"

# Cascade fail — abort entire downstream chain
cascade finish-task --task X --fail --cascade
```

## Orchestrator Guide

You are a **dynamic controller**, not a worker. You never claim or execute tasks. Your job is to build the DAG, dispatch workers, monitor progress, and adapt the plan.

### Rules

1. **Never claim tasks** — all execution is done by sub-agent workers
2. **Edges represent information needs** — if task B needs decisions/specs/APIs from task A, B depends on A. This is about what information flows, not code imports
3. **Promise = what the upstream delivers** — not what the downstream does

### Loop

1. **Create analyze node** — spawn a worker to analyze the problem and produce a detailed spec:
   - `summary`: overview of what was accomplished (propagates 2 hops)
   - `critical`: structured data downstream workers need (file paths, function lists, tech choices)
   - `artifacts`: full specification document
2. **Wait for analyze** — read the completed context to understand the problem space
3. **Build the DAG** — create N parallel tasks based on analyze output. Every independent module = separate task. More tasks = more parallelism
4. **Launch workers** — multiple Agent() calls in a single message = concurrent execution
5. **Review each completion** — when a worker finishes, check before moving on:
   - Did the worker fulfill its promises? Compare delivered context against its downstream promises
   - Is the task granularity right? A worker taking 3x longer than peers may need `split-node` next time
   - Did the worker report a hidden dependency or spec gap? → `refine-node` or `rework`
6. **Adapt the DAG** — the DAG is a living plan:
   - Worker reveals the task is too big → `split-node`
   - Worker output shows the spec was wrong → `rework`
   - Worker discovers a hidden dependency → `refine-node`
   - A task turns out unnecessary → `remove-node`
   - Tests could run in parallel → split test node into per-module test nodes
7. **Next wave** — launch workers for newly READY tasks
8. **Repeat** until all COMPLETED

The DAG evolves with your understanding. Early waves produce output that informs later planning — don't try to design the perfect DAG upfront.

### Sub-Agent Prompts

All specs live in critical/artifacts from the analyze phase. Workers get everything from `cascade get-task`. Do NOT duplicate spec in the prompt.

```
# RIGHT — zero-spec prompt, context flows through cascade
Agent({
  prompt: "cascade get-task --agent worker-1 --task impl-auth
           Read the upstream context. Do the work.
           cascade finish-task --task impl-auth --success --summary '...' --critical '{...}' --artifacts '...'"
})

# WRONG — duplicating spec in prompt
Agent({
  prompt: "Implement auth module: JWT tokens, refresh flow, password hashing...
           Write to src/auth.py with type hints..."
})
```

Why: spec in prompt = written N times, slower startup, stale if DAG changes. Spec in cascade = written once, flows automatically.

### When to Adjust

| Signal | Operation |
|--------|-----------|
| Task too large | `split-node` |
| Upstream output wrong | `rework` |
| Hidden dependency | `refine-node` |
| Task unnecessary | `remove-node` |
| Scope change | `edit-node` |
| Agent stalled | `check-timeouts` |
