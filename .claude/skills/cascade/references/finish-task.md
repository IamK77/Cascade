# finish-task

Complete, fail, or release a task. This is how you report work results and pass context to downstream tasks.

## Usage

```bash
cascade finish-task --task <task-id> [outcome] [context]
```

## Parameters

| Parameter | Short | Required | Description |
|-----------|-------|----------|-------------|
| `--task` | `-t` | Yes | Task ID to finish |
| `--token` | | **Yes** | Fencing token issued by `get-task` (in the briefing footer as `fencing_token: <int>`). Calls without it fail with `STALE_TOKEN`; stale tokens (after rework/release re-issued the node) also fail with `STALE_TOKEN` |
| `--agent` | `-a` | Yes | Agent ID — must match the claimer. The framework rejects mismatch with `WRONG_AGENT` |
| Outcome (pick one) |||
| `--success` | | No | Mark as COMPLETED, unblock dependents |
| `--fail` | | No | Mark as FAILED |
| `--release` | | No | Return to READY state |
| Context (optional) |||
| `--summary` | | No | Summary text for downstream tasks |
| `--critical` | | No | JSON object of key-value pairs |
| `--artifacts` | | No | Detailed output content |
| `--deliver NODE TEXT` | | Sometimes | Delivery confirmation addressed to a specific downstream promise (repeatable: `--deliver foo "..." --deliver bar "..."`). When the node has outstanding promises and no `--deliver` is provided, `--success` returns `UNADDRESSED_PROMISES`. Each pair is stored under `provenance.deliverables[NODE]` and shown in the consumer's briefing as `<source> delivered: <text>` |
| Failure options |||
| `--reason` | | No | Reason for fail/release |
| `--cascade` | | No | When failing, also fail all dependent tasks |

## Outcomes

### --success (Complete)

Task marked COMPLETED, downstream tasks unblocked.

```bash
cascade finish-task --task design --agent worker-1 --token <fencing-token> --success \
  --summary "UI design completed with Figma mockups" \
  --critical '{"component_count": 12, "design_system": "Material 3"}' \
  --artifacts "# Design System\n\n## Components\n- Button\n- Input\n- Form"
```

**What happens**:
1. Task state → COMPLETED
2. Readiness of all dependents recomputed from graph
3. Dependents with all dependencies COMPLETED become READY
4. Context (summary/critical/artifacts) propagates to downstream tasks

### --fail (Failure)

Task marked FAILED, downstream tasks blocked or cancelled.

```bash
# Simple failure - downstream blocked
cascade finish-task --task build --agent worker-1 --token <fencing-token> \
  --fail --reason "Compilation error in auth.ts"

# Cascade failure - downstream also fails
cascade finish-task --task api-core --agent worker-1 --token <fencing-token> \
  --fail --reason "Contract violation" --cascade
```

**What happens without --cascade**:
1. Task state → FAILED
2. Downstream tasks remain PENDING (blocked)

**What happens with --cascade**:
1. Task state → FAILED
2. All dependent tasks → CANCELLED
3. All their dependents → CANCELLED (recursive)

### --release (Return to pool)

Return task to READY state for retry.

```bash
cascade finish-task --task build --agent worker-1 --token <fencing-token> \
  --release --reason "Need more information"
```

**What happens**:
1. Task state → READY
2. `agent_id` cleared
3. Task can be claimed again

## Context Propagation

When you complete a task with context:

```
┌─────────────────┐
│ Task: design    │
│ summary: "..."  │────┐
│ critical: {...} │    │
│ artifacts: "..."│    │
└─────────────────┘    │
                       ▼
              ┌─────────────────┐
              │ Task: implement │
              │ Received:       │
              │ - summary       │
              │ - critical      │
              │ - artifacts     │
              └─────────────────┘
```

### critical (Key-Value Pairs)

Each upstream ancestor's critical is delivered as a separate entry — no merging, no overwriting across sources. Framework metadata (`produced_at` timestamp, `git_ref` HEAD commit) lives in a separate `provenance` field on each entry, **not** inside `critical`.

### summary (Text)

Each upstream's summary is a separate entry with provenance. Propagates within 2 hops.

### artifacts (Detailed Output)

Full content, propagated indefinitely via content-addressable storage.

## Output

```json
{
  "success": true,
  "message": "Task design completed",
  "data": {
    "task_id": "design",
    "outcome": "COMPLETED",
    "unblocked_tasks": ["implement", "api"]
  }
}
```

## Examples

### Complete with full context

```bash
cascade finish-task --task analyze --agent worker-1 --token <fencing-token> --success \
  --summary "Analyzed requirements, identified 3 core features" \
  --critical '{"features": ["auth", "dashboard", "api"], "tech_stack": "Next.js + FastAPI"}' \
  --artifacts "$(cat REQUIREMENTS.md)"
```

### Simple completion

```bash
cascade finish-task --task unit-tests --agent worker-1 --token <fencing-token> \
  --success --summary "All tests passing"
```

### Fail

```bash
cascade finish-task --task deploy --agent worker-1 --token <fencing-token> \
  --fail --reason "Environment not ready"
```
