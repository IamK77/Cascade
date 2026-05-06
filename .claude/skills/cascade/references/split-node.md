# split-node

Break a complex task into smaller subtasks. The original node is removed and replaced by the children.

## Usage

```bash
cascade split-node --parent <node-id> --children <child1,child2,...>
```

## Parameters

| Parameter | Short | Required | Description |
|-----------|-------|----------|-------------|
| `--parent` | `-p` | Yes | ID of the node to split |
| `--children` | `-c` | Yes | Comma-separated list of child node IDs |

## Inheritance Rules

When a parent is split, **all children inherit**:

| Property | Inheritance |
|----------|-------------|
| State | All children get parent's state |
| Dependencies | All children depend on what parent depended on |
| Dependents | All children become dependencies of parent's dependents |
| Contracts | Edge contracts are preserved from parent's edges |
| Readiness | Automatically recomputed from inherited dependencies |

## Graph Transformation

```
Before:  A → [parent] → D

After:   A → [child1] ┐
             → [child2] ├→ D
             → [child3] ┘
```

## Examples

### Split into parallel tasks

```bash
# Single large task
cascade add-node --id implement
cascade add-node --id test --deps implement

# Split into components
cascade split-node --parent implement --children auth,api,ui

# Result:
# auth, api, ui all depend on whatever "implement" depended on
# "test" now depends on ALL THREE: auth, api, ui
```

### Split from root

```bash
# Root task
cascade add-node --id project

# Split into parallel workstreams
cascade split-node --parent project --children frontend,backend,infra

# All three are now root nodes (no dependencies)
# Can be claimed by different agents simultaneously
```

## Use Cases

### 1. Decompose after analysis

```bash
# Agent analyzes and realizes task is too big
cascade finish-task --task analyze --success \
  --critical '{"subtasks": ["auth", "api", "ui"]}'

# Split based on analysis
cascade split-node --parent implement --children auth,api,ui
```

### 2. Parallel execution

```bash
# Create sequential plan initially
cascade add-node --id analyze
cascade add-node --id parallel-work --deps analyze
cascade add-node --id integrate --deps parallel-work

# Split parallel-work into actual parallel tasks
cascade split-node --parent parallel-work --children task-a,task-b,task-c

# Now task-a, task-b, task-c can run in parallel after analyze
# All three must complete before integrate
```

### 3. Add detail to placeholder

```bash
# High-level placeholder
cascade add-node --id feature-x

# Later, when scope is clear
cascade split-node --parent feature-x --children data-layer,biz-logic,api-layer,ui
```

## Output

```json
{
  "success": true,
  "message": "Node implement split into 3 children",
  "data": {
    "parent_id": "implement",
    "children": ["auth", "api", "ui"],
    "inherited_state": "PENDING",
    "affected_nodes": ["test"]
  }
}
```

## Error Cases

| Error | Cause | Solution |
|-------|-------|----------|
| `Parent node <id> not found` | Parent doesn't exist | Check node ID |
| `Node <id> is ACTIVE` | Can't split active task | Finish or release first |
| `Child ID <id> already exists` | Duplicate child ID | Use unique IDs |

## See Also

- [refine-node.md](refine-node.md) - Add single dependency
- [add-node.md](add-node.md) - Create individual nodes
