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

> Sections below marked **[L0]** = what you (orchestrator) do. **[L1]** = text to embed verbatim in worker prompts. Don't confuse them.

**[L0] Edges represent information needs** — if task B needs decisions/specs/APIs from task A, B depends on A. This is about information flow, not code imports.

### [L0] Spec Ownership

Every line of spec belongs to a node's artifacts. If you find yourself writing spec in an Agent prompt, find the node that should own it instead:

- Data shapes, types, constraints → analyze or schema node
- Public function signatures → the implementing node
- Cross-node conventions (state machines, error patterns) → analyze
- Internal implementation details → the worker itself

If a spec line has no node owner, your DAG is incomplete.

**Make semantics explicit.** `"computed": ["blocked_by"]` is ambiguous — workers may infer "computed field" but miss "therefore not persisted". Prefer: `{"blocked_by": {"type": "list[str]", "persist": false, "compute": "reverse of depends_on"}}`. Fields like `persist`, `validate`, `default` translate directly into worker code.

### [L0] Verification & Feedback Tools

- **`cascade inspect --task X`** — read-only preview of a worker's briefing plus its delivered context if completed. Use before dispatching (verify spec in place) and after (review what was delivered). Each `inspect` showing rich content is a credit signal that your DAG shape was right.
- **`cascade watch`** — long-running stream. Outputs one JSONL line per state transition; silent when idle. **Don't poll `list-nodes`** — that re-emits unchanged state every interval. Pair `watch` with your agent harness's monitor to react to `READY` (dispatch), `COMPLETED` (review), `FAILED` (decide). Each `COMPLETED` line in `watch` is a positive credit signal; `FAILED` / `release` are negative — inspect before redispatching.

### [L0] Loop

1. **Spawn analyze worker** — create a root analyze node, dispatch a worker to produce the spec (`summary` + `critical` + `artifacts`)
2. **Inspect analyze output** before designing the rest
3. **Build the DAG** — independent modules = separate tasks; more tasks = more parallelism
4. **Dispatch** workers for newly READY tasks
5. **Review** each completion via `inspect`; consult the **Adapt** table in SKILL.md and apply
6. **Next wave** — repeat until all COMPLETED

### [L1] Sub-Agent Prompts

> The text in this section is for embedding into worker Agent prompts, not for orchestrator behavior. Copy the template; the principle below explains why.

**Boundary principle**: cascade carries **intent** (state machines, invariants, cross-node conventions); upstream **code** carries **interface** (signatures, types, helpers). Both authoritative within their scope. From this:

- **Claim before any other tool.** First call MUST be `cascade get-task`. Otherwise LLMs translate "read upstream context" into `Read source.py` and become a ghost agent — DAG falsely READY while work happens off-DAG.
- **Read code for signatures, briefing for invariants.** Don't reconstruct interface from prose; don't reconstruct intent from code.
- **Release on missing intent.** If briefing lacks state machines, validation rules, or cross-cutting decisions, run `cascade finish-task --release --reason "Missing: <what>"`. Don't guess intent from code — it causes drift across siblings.

**Prompt template** — copy verbatim, replace `<node-id>` and `<agent-id>`:

```
RULE: Your first tool call MUST be `cascade get-task`. Until it succeeds,
do NOT use Read, Write, Edit, or any other tool.

1. Claim:
   cascade get-task --agent <agent-id> --task <node-id>

   On failure, STOP. Read the JSON's `code` field and act per the
   failure table below. Do not proceed.

2. Implement:
   The briefing carries intent (state machines, invariants, conventions).
   Read upstream code freely for signatures and patterns — both are
   authoritative for their respective scopes. If briefing lacks required
   intent (state rules, validation, contracts), release the task with
   --reason "Missing: <what>". Do not invent intent from code.

3. Finish:
   cascade finish-task --task <node-id> --agent <agent-id> --success \
       --summary "..." --critical '{...}' --artifacts "..."
```

**Pitfall**: `"Read upstream context"` in a prompt gets translated by LLMs into `Read` tool calls on source files, not `cascade get-task`. Be explicit about the command.

### [L1] Failure Codes

Workers branch on the JSON `code` field (not `message`). Run `cascade get-task --help` for the current full list; common cases:

| code | Action |
|------|--------|
| `TASK_NOT_READY` | Wait for upstream (use `cascade watch`) |
| `ALREADY_HAS_ACTIVE` | Finish your existing task before claiming a new one |
| `TASK_NOT_FOUND` | Report to orchestrator — DAG state mismatch |
| `TASK_ALREADY_ACTIVE` | Another agent has it; pick a different task |
| `WRONG_AGENT` | `--agent` doesn't match the claimer; check agent_id |
| `LOCK_CONTENTION` | Framework retried 3x; report and let orchestrator decide |
