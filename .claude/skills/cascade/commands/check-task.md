# check-task

Check whether a task claim is still valid. Pull-based cancellation interface for agent frameworks.

## Usage

```bash
cascade check-task --task <task-id>
```

## Parameters

| Parameter | Short | Required | Description |
|-----------|-------|----------|-------------|
| `--task` | `-t` | Yes | Task ID to check |

## Response

```json
{
  "success": true,
  "data": {
    "task_id": "analyze",
    "agent_id": "worker-1",
    "valid": true,
    "claimed_at": 1776937938.5,
    "reason": "",
    "invalidated_at": 0
  }
}
```

When invalidated:

```json
{
  "data": {
    "valid": false,
    "reason": "rework_requested",
    "invalidated_at": 1776938100.2
  }
}
```

## Invalidation Reasons

| Reason | Trigger |
|--------|---------|
| `released` | Agent called `finish-task --release` |
| `rework_requested` | Rework created a corrective node |
| `timed_out` | `check-timeouts` released the task |
| `no_token` | No active claim exists for this task |

## Notes

- This is for the **agent framework**, not the agent itself. The framework checks on behalf of the agent.
- Token is created on `get-task`, invalidated on release/rework/timeout, cleaned up on complete/fail.
- For push-based cancellation, register a `CancelNotifier` when claiming via the Python API.
