# list-nodes

View all tasks in the graph and their states.

## Usage

```bash
cascade list-nodes [options]
```

## Parameters

| Parameter | Short | Required | Description |
|-----------|-------|----------|-------------|
| `--state` | `-s` | No | Filter by state (READY, PENDING, ACTIVE, COMPLETED, FAILED) |
| `--pending-only` | | No | Show only PENDING tasks (waiting for dependencies) |

## Output

```json
{
  "success": true,
  "message": "Found 8 nodes",
  "data": {
    "nodes": [
      {
        "id": "analyze",
        "state": "COMPLETED",
        "pending_dependencies": 0,
        "agent_id": null
      },
      {
        "id": "design",
        "state": "READY",
        "pending_dependencies": 0,
        "agent_id": null
      },
      {
        "id": "implement",
        "state": "PENDING",
        "pending_dependencies": 1,
        "agent_id": null
      }
    ],
    "summary": {
      "PENDING": 3,
      "READY": 2,
      "ACTIVE": 1,
      "COMPLETED": 4,
      "FAILED": 0
    }
  }
}
```

## Examples

### List all nodes

```bash
cascade list-nodes
```

### Filter by state

```bash
# Tasks ready to be claimed
cascade list-nodes --state READY

# Tasks waiting for dependencies
cascade list-nodes --state PENDING

# Completed tasks
cascade list-nodes --state COMPLETED
```

### Show blocked tasks only

```bash
cascade list-nodes --pending-only
# Equivalent to --state PENDING
```

## State Meanings

| State | Meaning |
|-------|---------|
| PENDING | Has uncompleted dependencies, waiting |
| READY | All dependencies completed, can be claimed |
| ACTIVE | Being worked on by an agent |
| COMPLETED | Successfully finished |
| FAILED | Failed (possibly cascaded) |
| CANCELLED | Cancelled (possibly cascaded) |

## See Also

- [get-task.md](get-task.md) - Claim a READY task
