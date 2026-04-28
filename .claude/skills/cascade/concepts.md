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

Readiness is computed from the graph, never cached.

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

Direct parents (distance 1) include the edge contract; further ancestors include only `path` for provenance. Fan-in keeps each source separate — no key overwrite.

Three channels:

| Channel | Propagation | What to put | Example |
|---------|-------------|-------------|---------|
| `summary` | **2 hops only** | Text: what was accomplished | `"Designed 5 REST endpoints with JWT auth"` |
| `critical` | **All descendants** | Structured KV that downstream tasks need to make decisions | `{"endpoints": ["/users", "/auth"], "db": "PostgreSQL"}` |
| `artifacts` | **All descendants** | Full documents, specs, code — the complete deliverable | `"# API Spec\n## POST /auth/login\n..."` |

**Verify what workers see:** When a worker reports missing context, the data was never written upstream — propagation doesn't drop fields. Inspect the upstream node's completion in `cascade history --node <upstream>`.

## Contracts

Every edge carries `expectation` (consumer's requirement) and `promise` (what the **upstream** delivers).

Common mistake: writing the promise from the downstream's perspective ("Will provide CLI wiring" on an edge TO the CLI node). The promise should describe what the edge's source node delivers ("Provide project CRUD functions"). The framework warns on duplicate promises.

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

**Edges represent information needs** — if task B needs decisions/specs/APIs from task A, B depends on A. This is about what information flows, not code imports.

### Design Modes

Cascade is neutral on where decisions originate. Pick the mode that matches your situation:

- **Mode A** — You design, workers execute. Your blueprint lives in artifacts; analyze worker formats it. Use when you have clear architectural intent.
- **Mode B** — Workers design, you coordinate. analyze worker derives architecture from requirements; you set problem boundaries. Use when problem space is novel.

Both use the same machinery (contracts, propagation, rework). The difference is who holds the design pen.

### Spec Ownership

Every line of spec belongs to a node's artifacts. If you find yourself writing spec in an Agent prompt, find the node that should own it instead:

- Data shapes, types, constraints → analyze or schema node
- Public function signatures → the implementing node
- Cross-node conventions (state machines, error patterns) → analyze
- Internal implementation details → the worker itself

If a spec line has no node owner, your DAG is incomplete. **The closed-loop feeling of putting spec in prompts is working-memory proximity, not real observability — artifacts have the same observability (you wrote them too) without the cost of N-fold duplication.**

**Make semantics explicit, not implicit.** `"computed": ["blocked_by"]` is ambiguous — workers may infer "computed field" but miss "therefore not persisted". Prefer: `{"blocked_by": {"type": "list[str]", "persist": false, "compute": "reverse of depends_on"}}`. Fields like `persist`, `validate`, `default` translate directly into worker code without reading source files.

### Verification Tools

- `cascade inspect --task X` — read-only preview of the briefing a worker would see, plus delivered context if completed. Use before dispatching to verify spec is in place; use after completion to review delivered context.

### Edge-triggered Notifications

Don't poll `cascade list-nodes` in a loop — it's level-triggered (re-emits the same state every interval, high noise, latency tied to interval). Use `cascade watch` instead:

```bash
cascade watch
```

Long-running command. Outputs one JSONL line per state transition; silent when nothing changes. Pair with your agent harness's monitor to react to `READY` (dispatch), `COMPLETED` (review), `FAILED` (decide).

### Loop

1. **Spawn analyze worker** — create a root analyze node, dispatch a worker to produce the spec (`summary` + `critical` + `artifacts`)
2. **Inspect analyze output** — `cascade inspect --task analyze` to review what was delivered before designing the rest
3. **Build the DAG** — create parallel tasks. Every independent module = separate task. More tasks = more parallelism
4. **Dispatch workers** for newly READY tasks (parallel)
5. **Review and adapt** — for each completion, check whether the worker fulfilled its promises and whether the granularity was right:

   | Signal | Operation |
   |--------|-----------|
   | Task too large, or peer took 3x longer | `split-node` |
   | Upstream output wrong | `rework` |
   | Hidden dependency discovered | `refine-node` |
   | Task no longer needed | `remove-node` |
   | Scope change | `edit-node` |
   | Agent stalled | `check-timeouts` |

6. **Next wave** — dispatch workers for newly READY tasks; repeat until all COMPLETED

### Sub-Agent Prompts

Three mandatory rules — encode all three into every worker's prompt:

**Rule 1 — Tool ordering.** First tool call MUST be `cascade get-task`. Until it succeeds, do NOT use Read, Write, Edit, or any other tool. Without this, LLMs translate "read upstream context" into `Read /path/to/source.py`, skip cascade entirely, work for minutes, and leave the DAG falsely READY — the "ghost agent" pattern.

**Rule 2 — Briefing is the spec.** What `get-task` prints is the authoritative interface (types, signatures, conventions). After claiming, you MAY Read upstream source files for **style alignment** (naming patterns, error idioms, comment style), but never for **interface discovery**. Different agents reading source files independently invent inconsistent signatures.

**Rule 3 — Missing info → release, don't guess.** If the briefing lacks WHAT (a signature, field type, behavioral rule), do NOT fill the gap from source files. Run:

```
cascade finish-task --task <id> --agent <id> --release \
    --reason "Briefing missing: <specifically what>"
```

This escalates back so the orchestrator can fix the upstream artifact. Filling gaps locally causes interface drift across the DAG.

**Prompt template** — copy verbatim, replace `<node-id>` and `<agent-id>`:

```
RULE: Your first tool call MUST be `cascade get-task`. Until it succeeds,
do NOT use Read, Write, Edit, or any other tool.

1. Claim:
   cascade get-task --agent <agent-id> --task <node-id>

   If this fails, STOP. Read the JSON's `code` field and act per the
   failure table below. Do not proceed.

2. Implement:
   The briefing printed in step 1 IS your interface spec. Trust it.
   You may Read upstream source files for style alignment only — not
   to discover signatures. If briefing is missing required info,
   release the task instead of guessing.

3. Finish:
   cascade finish-task --task <node-id> --agent <agent-id> --success \
       --summary "..." --critical '{...}' --artifacts "..."
```

**Pitfall — `"Read upstream context"`** gets translated by LLMs into `Read` tool calls on source files, not into `cascade get-task`. Be explicit about the command.

### Failure Codes

`cascade get-task` and `finish-task` return JSON with a `code` field on failure (plus non-zero exit). Branch on `code`, not on `message`:

| code | What to do |
|------|-----------|
| `TASK_NOT_READY` | Wait for upstream completion (use `cascade watch`) |
| `ALREADY_HAS_ACTIVE` | Finish your existing task before claiming new |
| `TASK_NOT_FOUND` | Report to orchestrator — DAG state mismatch |
| `TASK_ALREADY_ACTIVE` | Another agent is on it; pick a different task |
| `WRONG_AGENT` | Your `--agent` doesn't match the claimer; check agent_id |
| `LOCK_CONTENTION` | Cascade already retried 3x; report and let orchestrator decide |
