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
| `--agent` | `-a` | Recommended | Agent ID — must match the claimer. Without it, no agent verification (returns success even if you didn't claim). With it, the framework rejects mismatch with `WRONG_AGENT`. Workers should always pass it |
| Outcome (pick one) |||
| `--success` | | No | Mark as COMPLETED, unblock dependents |
| `--fail` | | No | Mark as FAILED |
| `--release` | | No | Return to READY state |
| Context (optional) |||
| `--summary` | | No | Summary text for downstream tasks |
| `--critical` | | No | JSON object of key-value pairs |
| `--artifacts` | | No | Detailed output content |
| Failure options |||
| `--reason` | | No | Reason for fail/release |
| `--cascade` | | No | When failing, also fail all dependent tasks |

## Outcomes

### --success (Complete)

Task marked COMPLETED, downstream tasks unblocked.

```bash
cascade finish-task --task design --success \
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
cascade finish-task --task build --fail --reason "Compilation error in auth.ts"

# Cascade failure - downstream also fails
cascade finish-task --task api-core --fail --reason "Contract violation" --cascade
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
cascade finish-task --task build --release --reason "Need more information"
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

Merged from all upstream COMPLETED tasks:
```json
{
  "tech_stack": "Next.js",
  "component_list": ["Button", "Input"],
  "api_version": "v2"
}
```

Later tasks can override earlier values for same keys.

### summary (Text)

Concatenated from all upstream summaries:
```
[analyze] Requirements gathered...
[design] UI design completed...
```

### artifacts (Detailed Output)

Full content from immediate upstream, accessible but not automatically merged.

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
cascade finish-task --task analyze --success \
  --summary "Analyzed requirements, identified 3 core features" \
  --critical '{
    "features": ["auth", "dashboard", "api"],
    "tech_stack": "Next.js + FastAPI",
    "timeline": "2 weeks"
  }' \
  --artifacts "
# Requirements Analysis

## Features
1. **Authentication**: OAuth2 with Google/GitHub
2. **Dashboard**: Real-time metrics display
3. **API**: RESTful endpoints for CRUD operations

## Technical Decisions
- Frontend: Next.js 14 with App Router
- Backend: FastAPI with PostgreSQL
- Auth: Clerk for OAuth2
"
```

### Simple completion

```bash
cascade finish-task --task unit-tests --success --summary "All tests passing"
```

### Fail and retry later

```bash
cascade finish-task --task deploy --fail --reason "Environment not ready"
# Later, after fixing environment:
# Remove failed node and recreate, or use edit-node to reset state
```

## See Also

- [get-task.md](get-task.md) - Claim a task first
- [error-handling.md](../error-handling.md) - Recovery strategies
