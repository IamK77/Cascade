---
name: cascade
description: DAG-based multi-agent task coordination. Use when dispatching parallel sub-agents with dependencies, managing complex multi-step workflows, or coordinating worker agents through a DAG of tasks.
compatibility: opencode
metadata:
  audience: orchestrator
  workflow: multi-agent
---

# Cascade

DAG-based multi-agent task scheduling. You are the **orchestrator**: build the DAG, dispatch workers, adapt the graph. Never claim or execute tasks yourself — that's for worker sub-agents.

## Install

```bash
pipx install cascade-auto
# Verify: cascade --help
```

## Roles

| Role | Responsibility | Rule |
|------|---------------|------|
| **Orchestrator** (you) | Build DAG, adapt graph | Never claim tasks |
| **Worker** (sub-agent) | Self-claim any READY task, do work, finish, repeat | Stateless — claim → work → finish → claim next |

## Node States

| State | Meaning |
|-------|---------|
| `PENDING` | Has uncompleted dependencies |
| `READY` | All dependencies completed, can be claimed |
| `ACTIVE` | Being worked on by an agent |
| `COMPLETED` | Successfully finished |
| `FAILED` | Failed (possibly cascaded from upstream) |
| `CANCELLED` | Cancelled (possibly cascaded) |

Readiness is computed from the graph, never cached.

## Rules

1. **Contracts on edges** — every dependency has `expectation` (downstream need) + `promise` (upstream deliverable). Without contracts, workers hallucinate what upstream produced.
2. **Forward-only feedback** — rework creates corrective nodes, never reverse edges. No cycles.
3. **ACTIVE protection** — cannot remove/split nodes with active workers. Release or wait.
4. **Maximize parallelism** — independent tasks run concurrently. Split large tasks.

## Workflow

```
1. Build DAG        → cascade add-nodes --json '[...]'
2. Launch workers    → parallel task calls, each runs get-task (no --task) to self-claim
3. Monitor           → cascade watch or cascade list-nodes — observe completions/failures
4. Adapt             → split, rework, refine, remove, edit based on results
5. Repeat            → until all nodes COMPLETED
```

## Building the DAG

Batch form (preferred, atomic):

```bash
cascade add-nodes --json '[
  {"id": "analyze"},
  {"id": "design", "deps": ["analyze"],
   "expectations": [{"node_id": "analyze", "expectation": "Need data shapes", "promise": "Field definitions"}]},
  {"id": "implement", "deps": ["design"],
   "expectations": [{"node_id": "design", "expectation": "Need component spec", "promise": "Design doc"}]},
  {"id": "test", "deps": ["implement"]}
]'
```

If any spec fails validation, the entire batch is rejected — nothing partially added.

Single-node form:

```bash
cascade add-node --id <node-id> [--deps <dep1,dep2>]
```

## Dispatching Workers

Launch multiple workers in parallel via the task tool. Each worker runs the same prompt — `cascade get-task` without `--task` self-claims the highest-priority READY node. Cascade's critical-path scheduler naturally load-balances across however many workers are running. Workers are stateless and homogeneous.

Launch 3–6 workers for a typical DAG. Each worker loops: claim → work → finish → claim again, exiting when `NO_READY_TASKS`.

### [L1] Worker Prompt Template (copy verbatim)

```
RULE: Your first tool call MUST be `cascade get-task`. Until it succeeds,
do NOT use Read, Write, Edit, or any other tool.

LOOP:
  1. Claim any READY task:
     cascade get-task --agent <agent-id> --timeout 3600

     On NO_READY_TASKS: exit. All work done.
     On failure: read the JSON `code` field, act per the table below.

  2. Implement:
     The briefing carries intent (state machines, invariants, conventions).
     Read upstream code freely for signatures and patterns — both are
     authoritative within their scope. If the briefing lacks required
     intent (state rules, validation, contracts), release the task:
       cascade finish-task --task <claimed-id> --agent <agent-id> --release --reason "Missing: <what>"
     Do NOT invent intent from upstream code.

  3. Finish:
     cascade finish-task --task <claimed-id> --agent <agent-id> --success \
         --summary "What you accomplished" \
         --critical '{"key": "value"}' \
         --artifacts "Full deliverable content"

     Fail:
     cascade finish-task --task <claimed-id> --agent <agent-id> --fail --reason "Why"

     Cascade-fail (also fails all dependents):
     cascade finish-task --task <claimed-id> --agent <agent-id> --fail --cascade --reason "Why"

     Release (return to pool for retry):
     cascade finish-task --task <claimed-id> --agent <agent-id> --release --reason "Why"

     summary = 2-hop text description
     critical = KV pairs, propagate to all descendants
     artifacts = full documents/code, propagate indefinitely

  4. GOTO LOOP
```

### [L1] Worker Failure Codes

Workers branch on the JSON `code` field:

| code | Action |
|------|--------|
| `NO_READY_TASKS` | Exit — all available work is done |
| `ALREADY_HAS_ACTIVE` | Release previous task first: `finish-task --release` |
| `TASK_NOT_FOUND` | Report to orchestrator — DAG state mismatch |
| `WRONG_AGENT` | `--agent` doesn't match claimer; check agent_id |
| `LOCK_CONTENTION` | Framework retried 3x; retry claim after a short wait |

## Monitoring

Workers self-claim — the orchestrator does NOT dispatch on READY. Instead, monitor transitions to adapt the DAG.

**Prefer `cascade watch` over polling `list-nodes`.** Watch is edge-triggered — outputs one JSONL line per state transition, silent when idle. `list-nodes` re-emits unchanged state every call and wastes context.

```bash
# Stream state transitions (Ctrl-C to exit)
cascade watch
# Output per transition:
# {"type":"transition","node":"analyze","from":"PENDING","to":"READY","ts":1777400000.1}
# {"type":"transition","node":"analyze","from":"READY","to":"ACTIVE","agent":"worker-1","ts":1777400005.3}
```

React to transitions:
- `from:ACTIVE, to:COMPLETED` — worker delivered, inspect output, consider next DAG adaptation
- `from:ACTIVE, to:FAILED` — worker failed, decide: rework or remove
- `from:ACTIVE, to:READY` — worker released task, investigate reason
- `from:*, to:COMPLETED` accumulation without new ACTIVE — all workers exited? Check with `list-nodes`

Before dispatching a worker, verify its briefing with:
```bash
cascade inspect --task <node-id>
```
Inspect is read-only — shows the exact briefing + any delivered context if completed. If briefing is thin, enrich upstream artifacts first.

Periodically check for cancellation:
```bash
cascade check-task --task <node-id>
```

## Adapt

| Signal | Command | Behavior |
|--------|---------|----------|
| Task too large (peer 3x slower) | `split-node` | Split parent into parallel children; children inherit deps/dependents/contracts |
| Upstream output wrong/incomplete | `rework` | Create corrective node; requester returns to PENDING, waits for correction |
| Hidden dependency discovered | `refine-node` | Add dependency + contract to existing node |
| Task no longer needed | `remove-node` | Delete node (fails if it has dependents; use `--cascade` to recursively remove them) |
| Scope change, fix context | `edit-node` | Overwrite summary/artifacts, merge critical KV |
| Agent stalled | `check-timeouts` | Releases tasks past claimed_at + timeout |

### Key command forms

```bash
# Split
cascade split-node --parent implement --children impl-auth,impl-api

# Rework (forward-only — creates corrective, never reverses edges)
cascade rework --source analyze --corrective analyze-v2 --reason "Missing OAuth" \
  --agent agent-001 \
  --source-expectation "Original spec" --source-promise "First analysis" \
  --corrective-expectation "Revised spec with OAuth" --corrective-promise "Updated requirements"

# Refine
cascade refine-node --node deploy --dep security-review \
  --expectation "Security approval" --promise "Production credentials"

# Remove
cascade remove-node --node deprecated --cascade

# Edit (critical merges, summary/artifacts overwrite)
cascade edit-node --node design --critical '{"priority": "high"}'
```

## Failure Recovery

| Symptom | Recovery |
|---------|----------|
| Worker returns `ALREADY_HAS_ACTIVE` | `finish-task --release` its prior task, retry |
| `NO_READY_TASKS` but nodes still PENDING | Dependencies not met — check `list-nodes --state PENDING` for stuck upstream |
| `LOCK_CONTENTION` | Framework retries 3x; wait and retry |
| Worker finished but output wrong | `rework` — never edit a completed node's context |
| Worker stalled (no finish) | `check-timeouts`, inspect released task, re-dispatch or split |
| Nothing READY, graph stuck | `list-nodes` — look for PENDING cycles or forgotten ACTIVE tasks |
| All workers exited, graph not done | Re-launch workers — they'll pick up newly READY tasks. Loop until all COMPLETED |
| Workers overwrite each other's files | Launch with `isolation: "worktree"` in task tool |

## Context Channels

| Channel | Propagation | Use for |
|---------|-------------|---------|
| `summary` | 2 hops | Brief text: what was accomplished |
| `critical` | All descendants | Structured KV that downstream needs |
| `artifacts` | All descendants | Full documents, specs, code |

Provenance tracked per entry — fan-in keeps each source separate, no key overwrite.

## History

```bash
cascade history --summary      # event counts by type
cascade history --node <id>    # all events for a node
cascade history --last 5       # most recent events
```

Append-only `.cascade/events.jsonl` — full audit trail.
