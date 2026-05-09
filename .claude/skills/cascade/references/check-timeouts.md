# check-timeouts

Scan ACTIVE tasks and release any that have exceeded their timeout. This is a cooperative timeout — call it periodically as a watchdog.

## Usage

```bash
cascade check-timeouts [--default-timeout <seconds>]
```

## Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `--default-timeout` | No | Timeout in seconds for tasks without per-task timeout |

## How Timeouts Work

1. When claiming a task, set a timeout: `cascade get-task --agent x --timeout 3600`
2. The `claimed_at` timestamp is recorded on the node
3. `check-timeouts` scans ACTIVE nodes where `now - claimed_at >= timeout`
4. Expired tasks are released: ACTIVE → READY, agent cleared

```bash
# Per-task timeout (set at claim time)
cascade get-task --agent agent-1 --timeout 1800  # 30 minutes

# Default timeout (applied to tasks without per-task timeout)
cascade check-timeouts --default-timeout 3600  # 1 hour default
```

## Output

```json
{
  "success": true,
  "message": "Released 2 timed-out task(s)",
  "data": {
    "released": [
      {"task_id": "build", "agent_id": "agent-1", "elapsed_seconds": 4500.0, "timeout_seconds": 3600}
    ],
    "count": 2
  }
}
```

