# get-task

Claim an available task to work on. An agent can only hold one ACTIVE task at a time.

## Usage

```bash
cascade get-task --agent <agent-id> [options]
```

## Parameters

| Parameter | Short | Required | Description |
|-----------|-------|----------|-------------|
| `--agent` | `-a` | Yes | Unique agent identifier |
| `--task` | `-t` | No | Specific task ID to claim |
| `--timeout` | | No | Timeout in seconds (auto-release if exceeded) |

## Behavior

- **No --task**: Claims the first READY task (prioritized by critical path — most unblocking first)
- **With --task**: Claims specific task if it's READY
- **Agent already has task**: Returns reminder with current task info
- **No available tasks**: Returns error with available states

## Output

### Success

```json
{
  "success": true,
  "message": "Task <task-id> claimed by <agent-id>",
  "data": {
    "task_id": "<task-id>",
    "state": "ACTIVE",
    "context": {
      "critical": {...},      // Merged from upstream
      "summary": "...",       // Concatenated from upstream
      "artifacts": "..."      // Available for reading
    },
    "contracts": [            // What this task expects/promises
      {
        "node_id": "<upstream>",
        "expectation": "...",
        "promise": "..."
      }
    ],
    "visible_nodes": {...}    // Preview of downstream tasks
  }
}
```

### Already has task

```json
{
  "success": true,
  "message": "Agent <agent-id> already has task <current-task>",
  "data": {
    "reminder": true,
    "current_task": "<current-task>",
    "state": "ACTIVE"
  }
}
```

### No available tasks

```json
{
  "success": false,
  "message": "No READY tasks available",
  "data": {
    "pending_count": 3,
    "active_count": 1,
    "completed_count": 5
  }
}
```

## Examples

### Claim any available task

```bash
cascade get-task --agent claude-opus-4-6

# Returns first READY task with all upstream context
```

### Claim specific task

```bash
cascade get-task --agent claude-opus-4-6 --task auth-module

# Only claims if auth-module is READY
```

### Using session ID as agent

```bash
# Claude Code provides session ID
cascade get-task --agent "${CLAUDE_SESSION_ID}"
```

## Context Received

When claiming a task, you receive:

| Field | Source | Format |
|-------|--------|--------|
| `critical` | Merged from all upstream COMPLETED tasks | `{"key": "value"}` |
| `summary` | Concatenated from upstream summaries | Text |
| `artifacts` | From immediate upstream | Text/Markdown |
| `contracts` | Edge metadata from dependencies | Array |

## See Also

- [finish-task.md](finish-task.md) - Complete the claimed task
- [list-nodes.md](list-nodes.md) - Check available tasks first
