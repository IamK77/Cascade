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
| `--critical` | | No | JSON object to merge into critical context (override mode with `--context-merge`) |
| `--artifacts` | | No | New artifacts content (overwrites existing) |
| `--state` | | No | Manually set state (use with caution) |
| `--context-merge` | | No | How `--critical` combines with existing values: `merge` (default — shallow merge by key), `replace` (overwrite the whole dict), `append` (extend list-valued keys instead of replacing) |
| `--reason` | | No | Why this edit is needed (recorded in event log) |

## Merge vs Overwrite

| Field | Behavior |
|-------|----------|
| `--summary` | **Overwrites** existing summary |
| `--critical` | Default **merges** (shallow, by key); override with `--context-merge replace`/`append` |
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

