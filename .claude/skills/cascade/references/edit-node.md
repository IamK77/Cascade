# edit-node

Update task properties without changing the state flow. Useful for updating context while a task is ACTIVE or correcting information.

## Usage

```bash
cascade edit-node --node <node-id> [options]
```

## Parameters

| Parameter | Short | Required | Description |
|-----------|-------|----------|-------------|
| `--node` | `-n` | Yes | Node ID to edit |
| `--summary` | | No | New summary text (overwrites existing) |
| `--critical` | | No | JSON object to merge into critical context |
| `--artifacts` | | No | New artifacts content (overwrites existing) |
| `--state` | | No | Manually set state (use with caution) |

## Merge vs Overwrite

| Field | Behavior |
|-------|----------|
| `--summary` | **Overwrites** existing summary |
| `--critical` | **Merges** with existing critical values |
| `--artifacts` | **Overwrites** existing artifacts |
| `--state` | Directly sets state |

## Output

```json
{
  "success": true,
  "message": "Node task-1 updated",
  "data": {
    "node_id": "task-1",
    "changes": ["summary", "critical"]
  }
}
```

## Examples

### Update summary

```bash
cascade edit-node --node design --summary "UI design completed with Material 3 components"
```

### Update critical context (merge)

```bash
# Existing: {"tech_stack": "Next.js"}
# After:    {"tech_stack": "Next.js", "priority": "high"}

cascade edit-node --node design --critical '{"priority": "high"}'
```

### Replace critical entirely

```bash
# To replace instead of merge, set all keys
cascade edit-node --node design --critical '{"tech_stack": "React", "priority": "critical", "deadline": "2024-03-15"}'
```

### Update artifacts

```bash
cascade edit-node --node design --artifacts "
# Design System v2

## Color Palette
- Primary: #3B82F6
- Secondary: #10B981
- Error: #EF4444

## Typography
- Heading: Inter 600
- Body: Inter 400
"
```

### Manual state adjustment (caution)

```bash
# Force reset to READY (normally use --release)
cascade edit-node --node stuck-task --state READY
```

## Use Cases

### 1. Incremental updates while working

```bash
# Claim task
cascade get-task --agent agent-1

# Add notes as you work
cascade edit-node --node design --critical '{"progress": "50%"}'

# More notes
cascade edit-node --node design --critical '{"components_done": ["Button", "Input"]}'

# Complete
cascade finish-task --task design --success
```

### 2. Fix incorrect context

```bash
# Wrong value was set earlier
cascade edit-node --node analyze --critical '{"api_version": "v3"}'
# Now downstream tasks get correct version
```

### 3. Update before downstream uses it

```bash
# Task completed, but realized missing info
cascade edit-node --node design --artifacts "$(cat design-spec.md)"
```

### 4. Progress tracking

```bash
# Add checkpoint without finishing
cascade edit-node --node implement \
  --summary "Core logic done, testing remaining" \
  --critical '{"files_changed": 12, "tests_added": 8}'
```

## State Transitions

While `edit-node` can change state directly, prefer using proper commands:

| Desired State | Preferred Command |
|---------------|-------------------|
| READY | `finish-task --release` |
| ACTIVE | `get-task` |
| COMPLETED | `finish-task --success` |
| FAILED | `finish-task --fail` |

Only use `--state` for:
- Fixing stuck states
- Bulk corrections
- Recovery scenarios

## See Also

- [finish-task.md](finish-task.md) - Proper state transitions
- [get-task.md](get-task.md) - Claim tasks
- [list-nodes.md](list-nodes.md) - Check current values
