# remove-node

Delete a node from the graph.

## Usage

```bash
cascade remove-node --node <node-id> [options]
```

## Parameters

| Parameter | Short | Required | Description |
|-----------|-------|----------|-------------|
| `--node` | `-n` | Yes | Node ID to remove |
| `--cascade` | `-c` | No | Also remove all nodes that depend on this node |
| `--reason` | | No | Why this node is being removed (recorded in event log) |

## Behavior

### Without --cascade

- Fails if node has any dependents (nodes that depend on it)
- Removes node and all incoming edges
- Updates upstream nodes' adjacency lists

### With --cascade

- Removes the node
- Recursively removes all dependent nodes
- Useful for cleaning up after root cause failures

## Output

### Single node removal

```json
{
  "success": true,
  "message": "Node old-task removed",
  "data": {
    "removed_node": "old-task",
    "removed_edges": ["upstream → old-task"]
  }
}
```

### Cascade removal

```json
{
  "success": true,
  "message": "Removed 4 nodes (cascade)",
  "data": {
    "removed_nodes": ["root-task", "child-a", "child-b", "grandchild"],
    "cascade": true
  }
}
```

## Examples

### Remove leaf node (no dependents)

```bash
cascade remove-node --node old-feature
```

### Remove with dependents (cascade)

```bash
# Remove everything downstream
cascade remove-node --node failed-experiment --cascade

# Result: failed-experiment and all its dependents removed
```

### Clean up cancelled branch

```bash
# After cascade failure, clean up cancelled nodes
cascade list-nodes --state CANCELLED
cascade remove-node --node cancelled-root --cascade
```

## Error Cases

| Error | Cause | Solution |
|-------|-------|----------|
| `Node <id> not found` | Doesn't exist | Check node ID |
| `Node has dependents` | Has downstream nodes | Add `--cascade` or remove dependents first |
| `Node is ACTIVE` | Being worked on | Finish or release first |

## Recovery

If you accidentally remove nodes:
1. Recreate with `add-node`
2. Re-add dependencies with `refine-node`
3. Context from completed nodes is preserved in storage

