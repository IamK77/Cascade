# Core Concepts

## Node States

```
PENDING → READY → ACTIVE → COMPLETED
                    ↓  ↑       
                    ↓ release   
                    ↓  ↑       
                    → READY     
                    ↓
                    → FAILED
                    ↓
                    → CANCELLED

Any non-terminal → FAILED (cascade failure)
Any non-terminal → CANCELLED (cascade cancel)
```

| State | Meaning |
|-------|---------|
| PENDING | Has uncompleted dependencies, must wait |
| READY | All dependencies completed, can be claimed |
| ACTIVE | Being worked on by an agent |
| COMPLETED | Successfully finished |
| FAILED | Failed (possibly cascaded from upstream) |
| CANCELLED | Cancelled (possibly cascaded from upstream) |

### Readiness is Computed, Not Stored

There is no `in_degree` field on nodes. Readiness is **derived from the graph**:

```
A node is READY when:
  count(dependencies where state ≠ COMPLETED) == 0
```

This means:
- You never need to manually track dependency counts
- Readiness is always consistent, even after split/refine/rework
- The system recomputes readiness whenever edges change

## Context Propagation

Context flows **downstream** from COMPLETED tasks. Each upstream contribution is kept separate and attributed by the promise on the connecting edge.

| Channel | Propagation | At Fan-In |
|---------|-------------|-----------|
| `critical` | Indefinitely (all descendants) | Separate per source |
| `summary` | 2 hops (children + grandchildren) | Separate per source |
| `artifacts` | Indefinitely (file reference) | Separate per source |

```
┌─────────────────────┐
│ Task: analyze       │
│ State: COMPLETED    │
│ summary: "..."      │──────────┐
│ critical: {k1: v1}  │          │ attributed by
│ artifacts: "..."    │          │ edge promise
└─────────────────────┘          │
                                 ↓
                    ┌──────────────────────────┐
                    │ Task: design             │
                    │ State: ACTIVE            │
                    │ context: [               │
                    │   {promise: "...",        │
                    │    summary: "...",        │
                    │    critical: {k1: v1}}    │
                    │ ]                        │
                    └──────────────────────────┘
```

### Your Output IS Your Fulfilled Promise

When you `finish-task --success`, your `summary`, `critical`, and `artifacts` become the context that downstream agents receive — tagged with your edge promise. This is how you fulfill the contract.

## Contracts on Edges

Every edge carries a contract with two fields:

- **expectation**: what the **downstream node** needs from this upstream — written from the consumer's perspective
- **promise**: what the **upstream node** commits to deliver — written from the producer's perspective

```
     auth (upstream)
       │
       │  promise: "Provide JWT tokens and user session"     ← auth's commitment
       │  expectation: "Need auth tokens for API calls"      ← api's requirement
       ↓
     api (downstream)
```

**Common mistake**: writing promise as the downstream's output ("Provide API endpoints"). Promise describes what the UPSTREAM delivers, not what the downstream will produce. The framework warns if multiple edges to the same node have identical promises — that usually means they were written from the wrong perspective.

Different downstream nodes can have **different contracts** with the same upstream:

```
     auth ──→ api         expectation: "Auth tokens"       promise: "JWT + refresh token"
     auth ──→ websocket   expectation: "Session ID"        promise: "Session cookie"
```

## Rework (Forward-Only Feedback)

When an agent discovers upstream output is wrong, it doesn't "go back" — it **derives a corrective node** that grows the graph forward:

```
Before:  A(COMPLETED) → B(ACTIVE, discovers problem)

After:   A(COMPLETED) → A'(READY, corrective task) → B(PENDING, waits)
         A(COMPLETED) → B(PENDING, waits for A')
```

A' depends on A (sees original output), B depends on A' (waits for correction). The contract on A'→B describes what needs to be different. No reverse edges, no cycles.

## Critical Path Scheduling

When multiple tasks are READY, Cascade prioritizes by **downstream depth** — the task that unblocks the most downstream work is scheduled first. This is computed via topological-order dynamic programming.

## Event Sourcing

Every action is recorded in `.cascade/events.jsonl`:
- `node_added`, `task_claimed`, `task_completed`, `task_failed`
- `task_released`, `task_timed_out`, `rework_requested`

Query with `cascade history --summary` or `cascade history --node <id>`.

## Independent Task Groups

Multiple disconnected subgraphs are allowed. You can have parallel independent workflows in the same Cascade instance.

## Orchestrator Behavior Guide

The orchestrator (main agent using Cascade) is a **dynamic controller**, not a static planner. The initial DAG is a starting hypothesis.

### Orchestrator Loop

```
1. Build initial DAG — split tasks horizontally for maximum parallelism
2. Launch workers on READY tasks (via Agent tool)
3. When a worker completes:
   a. Read its output (summary, critical, artifacts)
   b. Decide: is the DAG still correct?
   c. If not → adjust (split, rework, refine, remove, edit)
4. Launch next wave of workers on newly READY tasks
5. Repeat until all tasks COMPLETED
```

### Parallel Execution with Sub-Agents

Use the Agent tool to run multiple workers simultaneously. Each sub-agent claims one task, does the work, and exits.

**Step 1: Build DAG and complete the analysis task yourself**

```bash
cascade add-node --id analyze
cascade get-task --agent orchestrator
# Do the analysis work...
cascade finish-task --task analyze --success \
  --summary "Spec: 4 modules..." \
  --critical '{"modules": ["auth", "users", "posts", "search"]}'
```

**Step 2: Create parallel tasks depending on analyze**

```bash
cascade add-node --id impl-auth --deps analyze --expectations '[...]'
cascade add-node --id impl-users --deps analyze --expectations '[...]'
cascade add-node --id impl-posts --deps analyze --expectations '[...]'
cascade add-node --id impl-search --deps analyze --expectations '[...]'
```

**Step 3: Launch sub-agents in parallel (single message, multiple Agent calls)**

```
Agent({
  prompt: "You are a worker. Run: cascade get-task --agent worker-1 --task impl-auth
           Read the upstream context. Do the work. Then:
           cascade finish-task --task impl-auth --success --summary '...' --critical '{...}'"
})
Agent({
  prompt: "You are a worker. Run: cascade get-task --agent worker-2 --task impl-users ..."
})
Agent({
  prompt: "You are a worker. Run: cascade get-task --agent worker-3 --task impl-posts ..."
})
Agent({
  prompt: "You are a worker. Run: cascade get-task --agent worker-4 --task impl-search ..."
})
```

All 4 agents run concurrently. When they complete, check progress:

```bash
cascade list-nodes
cascade history --summary
```

**Step 4: Continue with next wave**

Repeat Step 3 for newly READY tasks until all tasks are COMPLETED.

**Key rules for sub-agent prompts:**
- **Keep prompts minimal** — only task ID + basic instructions. Do NOT copy context into the prompt.
- All context flows through Cascade: `cascade get-task` returns upstream deliveries, contracts, and promises.
- Putting context in the Agent prompt bypasses Cascade's context system AND makes agent startup slower.
- Tell the worker to call `cascade finish-task` with summary + critical when done.
- Workers should NOT explore the workspace — everything they need is in the get-task output.

### When to Use Each DAG Operation

| Signal | Operation | Example |
|--------|-----------|---------|
| Worker reports task is too large | `split_node` | "This module has 3 independent parts" |
| Worker output contradicts upstream | `rework` | "The API spec is missing auth endpoints" |
| Implementation reveals hidden dependency | `refine_node` | "Frontend needs the DB schema first" |
| Task becomes unnecessary | `remove_node` | "We don't need a separate config module" |
| Task scope needs adjustment | `edit_node` | "Only implement the core, skip CLI" |
| Worker stalls | `check_timeouts` | Agent exceeds timeout → task released |

### Maximizing Parallelism

**Default to wide, not deep.** Prefer:

```
     A
   / | \
  B  C  D     ← 3 parallel workers
   \ | /
     E
```

Over:

```
  A → B → C → D → E     ← serial, slow
```

Split aggressively at the planning stage. If a task has 3 independent subtasks, split immediately — don't wait for an agent to discover this.

### Context Discipline

Each worker should output:
- **summary**: One sentence — what was accomplished
- **critical**: Structured KV — decisions, configs, endpoints, counts that downstream needs
- **artifacts**: Full content — code, specs, detailed docs

The orchestrator should verify that critical data flows correctly through the DAG. If a downstream worker is missing data it needs, either:
- The upstream worker forgot to include it → `rework`
- A dependency edge is missing → `refine_node`
