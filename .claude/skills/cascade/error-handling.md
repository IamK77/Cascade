# Error Handling

## Failure Scenarios

### 1. Task Failure (--fail)

Task fails but downstream tasks are just blocked.

```bash
cascade finish-task --task build --fail --reason "Compilation error in auth.ts"
```

**What happens**:
- Task state → FAILED
- Downstream tasks remain PENDING (blocked by this failure)
- They can proceed once the issue is fixed

**Recovery**:
```bash
# Option 1: Fix the issue and retry
cascade edit-node --node build --state READY
cascade get-task --agent agent-1 --task build

# Option 2: Remove and recreate
cascade remove-node --node build
cascade add-node --id build --deps analyze
```

### 2. Cascade Failure (--fail --cascade)

Task fails and all dependent tasks are cancelled.

```bash
cascade finish-task --task api-core --fail --reason "Contract violation" --cascade
```

**What happens**:
- Task state → FAILED
- All direct dependents → CANCELLED
- All transitive dependents → CANCELLED (recursive)

**Recovery**:
```bash
# Must remove cancelled nodes and rebuild
cascade list-nodes --state CANCELLED
cascade remove-node --node cancelled-root --cascade

# Rebuild the affected portion
cascade add-node --id new-api-core --deps fixed-upstream
```

### 3. Release (--release)

Return task to pool without failure.

```bash
cascade finish-task --task build --release --reason "Need more information from design"
```

**What happens**:
- Task state → READY
- Agent assignment cleared
- Downstream tasks unaffected
- Another agent can claim this task

**Use cases**:
- Blocked on external information
- Realized wrong task claimed
- Transient error that may resolve

## Downstream Impact Summary

| Failure Type | Downstream State | Recovery Complexity |
|--------------|------------------|---------------------|
| `--fail` | PENDING (blocked) | Low - fix and retry |
| `--fail --cascade` | CANCELLED | High - must rebuild |
| `--release` | Unaffected | None - just retry |

## Recovery Strategies

### Strategy 1: Fix and Continue

Best for transient errors or fixable issues.

```bash
# 1. Task failed
cascade finish-task --task build --fail --reason "Missing dependency"

# 2. Install missing dependency
npm install missing-package

# 3. Reset and retry
cascade edit-node --node build --state READY
cascade get-task --agent agent-1 --task build
cascade finish-task --task build --success
```

### Strategy 2: Release and Retry

Best when blocked on external factors.

```bash
# 1. Blocked on external info
cascade finish-task --task design --release --reason "Waiting for client feedback"

# 2. Do other work
cascade get-task --agent agent-1  # Get different task

# 3. Come back when unblocked
cascade get-task --agent agent-1 --task design
```

### Strategy 3: Rebuild Subgraph

Best after cascade failures.

```bash
# 1. Core failure cascaded
cascade finish-task --task auth --fail --reason "Architecture decision" --cascade
# auth, api, frontend all CANCELLED

# 2. Remove cancelled nodes
cascade remove-node --node auth --cascade  # Removes all cancelled

# 3. Rebuild with new approach
cascade add-node --id auth-v2 --deps design
cascade add-node --id api-v2 --deps auth-v2
cascade add-node --id frontend-v2 --deps auth-v2
```

### Strategy 4: Parallel Alternative

Best when original approach is uncertain.

```bash
# Keep failed node, create alternative
cascade finish-task --task approach-a --fail --reason "Performance issues"

# Try different approach in parallel
cascade add-node --id approach-b --deps same-upstream

# If approach-b succeeds, clean up approach-a
cascade finish-task --task approach-b --success
cascade remove-node --node approach-a
```

## Common Error Patterns

### Circular Dependency

```
Error: Adding edge api → auth would create a cycle
```

**Cause**: auth → api already exists

**Solution**:
```bash
# Restructure to remove cycle
# Create shared dependency instead
cascade add-node --id shared-auth-types
cascade refine-node --node auth --dep shared-auth-types
cascade refine-node --node api --dep shared-auth-types
# Remove the circular edge (requires manual graph edit or recreate)
```

### Agent Already Has Task

```
Error: Agent agent-1 already has active task: task-y
```

**Solution**:
```bash
# Finish current task first
cascade finish-task --task task-y --success

# Then get new task
cascade get-task --agent agent-1
```

### Task Not Ready

```
Error: Task task-z is not READY (current: PENDING)
```

**Cause**: Task still has incomplete dependencies

**Solution**:
```bash
# Check what's blocking
cascade list-nodes --state PENDING

# Complete blocking tasks first
cascade get-task --agent agent-2 --task blocking-task
cascade finish-task --task blocking-task --success
```

## Best Practices

1. **Use --release for transient issues** - Keeps graph intact
2. **Use --fail for real problems** - Signals downstream
3. **Use --cascade only when necessary** - Recovery is expensive
4. **Check state before claiming** - `list-nodes --state READY`
5. **Provide clear reasons** - Helps downstream agents understand the issue
