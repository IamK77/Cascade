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
| `--task` | `-t` | No | Specific task ID to claim. Without it, the highest-priority READY task is claimed (critical-path first) |
| `--timeout` |  | No | Seconds before auto-release if not finished |

## Output

### Success → markdown briefing

On success, the CLI prints a **markdown briefing** to stdout (not JSON). Sections:

```markdown
# Task: <task-id>

## Upstream Context

### <upstream-id> (direct dependency)
- **Expects from you**: <what consumer needs>
- **Promised to deliver**: <what upstream provided>
- **Summary**: <upstream summary>
- **Critical data**:
  ```json
  {...}
  ```
- **Artifacts**: <full content>

## Promises to Downstream
- → <downstream-id>: <promise text>

## Downstream Topology
- <node> (<state>, distance N)
```

The briefing IS the worker's spec. Read it before doing any other tool call. Do not Read source files to discover the interface.

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

## See also

- [finish-task.md](finish-task.md) — complete the claimed task
- [inspect.md](inspect.md) — read-only preview without claiming
