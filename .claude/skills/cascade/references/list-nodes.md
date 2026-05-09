# list-nodes

View all tasks in the graph and their states.

## Usage

```bash
cascade list-nodes [options]
```

## Parameters

| Parameter | Short | Required | Description |
|-----------|-------|----------|-------------|
| `--state` | `-s` | No | Filter by state (PENDING, READY, ACTIVE, COMPLETED, FAILED, CANCELLED) |
| `--pending-only` | | No | Show only PENDING tasks (waiting for dependencies) |

## Output

```json
{
  "success": true,
  "message": "Listed 8 nodes",
  "data": {
    "nodes": [
      {
        "id": "analyze",
        "state": "COMPLETED",
        "pending_dependencies": 0
      },
      {
        "id": "impl-auth",
        "state": "ACTIVE",
        "pending_dependencies": 0,
        "agent_id": "worker-1",
        "active_seconds": 42.3
      },
      {
        "id": "impl-stalled",
        "state": "ACTIVE",
        "pending_dependencies": 0,
        "agent_id": "worker-2",
        "active_seconds": 1820.7,
        "stale": true
      },
      {
        "id": "design",
        "state": "READY",
        "pending_dependencies": 0
      },
      {
        "id": "implement",
        "state": "PENDING",
        "pending_dependencies": 1
      }
    ],
    "count": 5,
    "by_state": {
      "COMPLETED": ["analyze"],
      "ACTIVE": ["impl-auth", "impl-stalled"],
      "READY": ["design"],
      "PENDING": ["implement"]
    }
  }
}
```

ACTIVE nodes include `agent_id` and `active_seconds`; `stale: true` flags nodes either timed out or ACTIVE for >10 minutes without an explicit timeout.

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

For state meanings, see [concepts.md](../concepts.md#node-states).
