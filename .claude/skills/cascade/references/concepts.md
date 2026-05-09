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
        "critical": {"auth": "JWT", "db": "PostgreSQL"},
        "provenance": {"produced_at": 1778050765.98, "git_ref": "a3f8c2e..."}
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

Each upstream entry's `provenance` carries framework metadata (`produced_at`, `git_ref`, per-target `deliverables`) — distinct from `critical`, which holds only user-supplied KV.

## Fencing Tokens

`get-task` issues a fencing token in the briefing footer (`fencing_token: <int>`). `finish-task` requires it via `--token`; calls without it fail with `STALE_TOKEN`. The framework also rejects tokens older than the node's current epoch — so workers whose claims were invalidated by `rework` or `release` cannot silently overwrite the freshly-claimed worker's results.

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

Workers self-contain the protocol (see `.claude/agents/cascade-worker.md`). Dispatch them with a unique `agent-id`; cascade auto-schedules the task. The sections below are for you, the orchestrator.

**Edges represent information needs** — if task B needs decisions/specs/APIs from task A, B depends on A. This is about information flow, not code imports.

### Spec Ownership

Every line of spec belongs to a node's artifacts. If you find yourself writing spec in an Agent prompt, find the node that should own it instead:

- Data shapes, types, constraints → analyze or schema node
- Public function signatures → the implementing node
- Cross-node conventions (state machines, error patterns) → analyze
- Internal implementation details → the worker itself

If a spec line has no node owner, your DAG is incomplete.

**Make semantics explicit.** `"computed": ["blocked_by"]` is ambiguous — workers may infer "computed field" but miss "therefore not persisted". Prefer: `{"blocked_by": {"type": "list[str]", "persist": false, "compute": "reverse of depends_on"}}`. Fields like `persist`, `validate`, `default` translate directly into worker code.

### Verification & Feedback Tools

- **`cascade inspect --task X`** — read-only preview of a worker's briefing plus its delivered context if completed. Use before dispatching (verify spec in place) and after (review what was delivered). Each `inspect` showing rich content is a credit signal that your DAG shape was right.
- **`cascade watch`** — long-running stream. Outputs one JSONL line per state transition; silent when idle. **Don't poll `list-nodes`** — that re-emits unchanged state every interval. Pair `watch` with your agent harness's monitor to react to `READY` (dispatch), `COMPLETED` (review), `FAILED` (decide). Each `COMPLETED` line in `watch` is a positive credit signal; `FAILED` / `release` are negative — inspect before redispatching.

### Loop

1. **Spawn analyze worker** — create a root analyze node, dispatch a worker to produce the spec (`summary` + `critical` + `artifacts`)
2. **Inspect analyze output** before designing the rest
3. **Build the DAG** — independent modules = separate tasks; more tasks = more parallelism
4. **Dispatch** workers for newly READY tasks
5. **Review** each completion via `inspect`; consult the **Adapt** table in SKILL.md and apply
6. **Next wave** — repeat until all COMPLETED

