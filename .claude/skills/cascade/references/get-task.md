# get-task

Claim an available task. An agent can hold only one ACTIVE task at a time.

## Usage

```bash
cascade get-task --agent <agent-id> [--task <task-id>] [--timeout <seconds>]
```

## Parameters

| Parameter | Short | Required | Description |
|-----------|-------|----------|-------------|
| `--agent` | `-a` | Yes | Unique agent identifier — must match the agent passed to `finish-task` |
| `--task` | `-t` | No | Specific task ID to claim. **Workers should omit this** — cascade auto-schedules by critical-path priority, and manual selection defeats the scheduler. Use only for orchestrator-side targeted retry/inspection |
| `--timeout` |  | No | Seconds before auto-release if not finished |

## Output

### Success → plain-text briefing

On success, the CLI prints a **plain-text briefing** to stdout (not JSON or
Markdown). Sections use `[bracket-tagged]` headers and indented bodies.
The footer carries the **fencing token** required for `finish-task`.

```
Task: <task-id>

[upstream: <upstream-id>, direct]
  you expected: <consumer's need>
  <upstream-id> promised: <upstream's deliverable>
  <upstream-id> delivered: <text addressed to this task, if any>
  summary: <upstream summary>
  freshness: <elapsed> | <commits behind HEAD>
  critical: {"k": "v"}
  artifacts:
    |# Markdown body
    |...

[upstream: <ancestor-id>, distance 2]
  ...

[promises]
  <downstream-id> expects: <expectation text>
  you promise: <promise text>

[downstream]
  <id> (<STATE>, distance 1)

---
fencing_token: 17
```

The briefing IS the worker's spec — read it before any other tool call;
do not Read source files to discover the interface.

**The `fencing_token` integer is mandatory input to `finish-task`.** Pass
it via `--token <int>`; calls without it fail with `STALE_TOKEN`. Provenance
metadata (`produced_at`, `git_ref`) lives in a separate `provenance` field
on each upstream entry — use the `freshness:` line if you need it.

### Failure → JSON with `code`

```json
{
  "success": false,
  "message": "...",
  "code": "<ERROR_CODE>",
  "data": {...}
}
```

Failures emit non-zero exit code. Common codes:

| code | Cause |
|------|-------|
| `TASK_NOT_FOUND` | `--task` ID doesn't exist |
| `TASK_NOT_READY` | Task is PENDING (deps not met) |
| `TASK_TERMINAL` | Task already COMPLETED/FAILED/CANCELLED |
| `TASK_ALREADY_ACTIVE` | Another agent holds the task |
| `ALREADY_HAS_ACTIVE` | This agent already holds a different active task — finish it first |
| `NO_READY_TASKS` | No --task specified, nothing READY in the graph |
| `MISSING_AGENT_ID` | `--agent` not provided |
| `LOCK_CONTENTION` | Storage lock unavailable after 3 retries |

## Examples

```bash
# Claim highest-priority READY task
cascade get-task --agent worker-1

# Claim specific task
cascade get-task --agent worker-1 --task impl-auth

# Claim with auto-release after 1 hour
cascade get-task --agent worker-1 --task slow-task --timeout 3600
```

