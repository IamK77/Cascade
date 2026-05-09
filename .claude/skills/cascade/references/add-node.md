# add-node

Create a new task node in the DAG.

## Usage

```bash
cascade add-node --id <node-id> [options]
```

## Parameters

| Parameter | Short | Required | Description |
|-----------|-------|----------|-------------|
| `--id` | `-i` | Yes | Unique node identifier |
| `--deps` | `-d` | No | Comma-separated list of dependency node IDs |
| `--dependents` | `-D` | No | Comma-separated list of node IDs that will depend on this node |
| `--expectations` | `-e` | No | JSON array of contracts |

## Behavior

- **Any node**: Can be created with or without dependencies
- **Independent roots**: Multiple disconnected task groups are allowed
- **State**: Auto-computed — READY if no pending dependencies, PENDING otherwise
  - No dependencies OR all dependencies completed → READY
  - Has pending dependencies → PENDING

## Output

```json
{
  "success": true,
  "message": "Node <id> added successfully",
  "data": {
    "node_id": "<id>",
    "state": "READY|PENDING",
    "affected_nodes": ["<id>", ...]
  }
}
```

## Examples

### Basic task

```bash
cascade add-node --id analyze
# State: READY (no dependencies)
```

### With dependencies

```bash
cascade add-node --id design --deps analyze
# State: PENDING (waiting for analyze)
```

### Multiple dependencies

```bash
cascade add-node --id integrate --deps auth,api,ui
# State: PENDING (waiting for all three)
```

### With dependents (reverse direction)

```bash
# Existing: analyze -> design
# Add new prerequisite:
cascade add-node --id requirements --dependents analyze
# Result: requirements -> analyze -> design
```

### With expectations (contracts)

```bash
cascade add-node --id auth-module --deps base-components \
  --expectations '[
    {
      "node_id": "base-components",
      "expectation": "Need Button, Input, Form components",
      "promise": "Will provide Login and Register forms"
    }
  ]'
```

## Error Cases

| Error | Cause | Solution |
|-------|-------|----------|
| `Node <id> already exists` | Duplicate ID | Use unique ID |
| `Dependency <id> not found` | Dep node doesn't exist | Create dependency first |
| `Would create a cycle` | Adding edge would create circular dependency | Restructure |
