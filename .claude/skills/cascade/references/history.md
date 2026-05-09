# history

Query the append-only event log. Every significant action is recorded in `.cascade/events.jsonl`.

## Usage

```bash
cascade history [options]
```

## Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `--node` | No | Filter events for a specific node |
| `--type` | No | Filter by event type |
| `--last` | No | Show only the last N events |
| `--summary` | No | Show event counts by type |

## Event Types

| Type | When |
|------|------|
| `node_added` | New node created |
| `node_removed` | Node deleted |
| `node_edited` | `edit-node` updated a node's properties |
| `node_split` | `split-node` replaced a parent with children |
| `node_refined` | `refine-node` added a dependency |
| `node_cancelled` | Node CANCELLED by cascade failure |
| `edge_added` | Dependency edge created (via `add-node` deps or `refine-node`) |
| `edge_removed` | Dependency edge deleted |
| `task_claimed` | Agent claims a task (`get-task`) |
| `task_completed` | Task finished successfully |
| `task_failed` | Task failed |
| `task_released` | Task returned to pool |
| `task_timed_out` | Task auto-released by `check-timeouts` |
| `rework_requested` | Corrective node created (`rework`) |

## Examples

```bash
# Summary of all events
cascade history --summary
# → node_added: 4, task_claimed: 4, task_completed: 3, rework_requested: 1

# Events for a specific node
cascade history --node analyze
# → node_added, task_claimed (by agent-1), task_completed

# Last 5 events
cascade history --last 5

# All rework events
cascade history --type rework_requested
```

## Output

```json
{
  "success": true,
  "data": {
    "events": [
      {"type": "task_claimed", "timestamp": "2026-04-14T...", "data": {"node_id": "analyze", "agent_id": "agent-1"}}
    ],
    "count": 1
  }
}
```

## Audit verbs

The event log is content-addressed (SHA-256 chain) and supports time-travel
via **logical timestamps** — monotonic event-sequence numbers, not wall-clock
time:

| Command | Use |
|---------|-----|
| `cascade show --ts <N>` | Print the event at logical timestamp `N` |
| `cascade diff --from <A> --to <B>` | Print events between two logical timestamps |
| `cascade snapshot-at --ts <N>` | Replay events to rebuild graph state as of `N` |
| `cascade verify-chain` | Verify the SHA-256 hash chain integrity of the entire log |

