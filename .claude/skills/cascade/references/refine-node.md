# refine-node

Add a dependency to an existing node with optional contract metadata.

## Usage

```bash
cascade refine-node --node <node-id> --dep <dependency-id> [options]
```

## Parameters

| Parameter | Short | Required | Description |
|-----------|-------|----------|-------------|
| `--node` | `-n` | Yes | Node to add dependency to |
| `--dep` | `-d` | Yes | Dependency node ID |
| `--expectation` | | No | What this node expects from the dependency |
| `--promise` | | No | What the dependency promises to provide |
| `--reason` | | No | Why this dependency is needed (recorded in event log) |

## Behavior

- Creates edge: `dependency → node`
- Readiness recomputed: if node was READY and dependency is uncompleted, it becomes PENDING
- Stores expectation/promise (contract) on the edge

## Output

```json
{
  "success": true,
  "message": "Dependency added: security-review → deploy",
  "data": {
    "node_id": "deploy",
    "new_dependency": "security-review",
    "pending_dependencies": 2,
    "contract": {
      "expectation": "Security approval",
      "promise": "Deployment credentials"
    }
  }
}
```

## Examples

### Add simple dependency

```bash
# deploy now depends on security-review
cascade refine-node --node deploy --dep security-review
```

### Add with contract

```bash
# Define what's expected and promised
cascade refine-node --node deploy --dep security-review \
  --expectation "Security scan approval" \
  --promise "Production deployment rights"
```

### Add multiple dependencies

```bash
# One at a time
cascade refine-node --node deploy --dep security-review
cascade refine-node --node deploy --dep load-test
cascade refine-node --node deploy --dep documentation
```

## Edge Metadata

Contracts are stored per-edge, allowing different promises to different downstream tasks:

```
          ┌────────────────────────────────────────┐
          │         ↓ expectation: "Auth tokens"   │
          │         ↓ promise: "User context"      │
          │                                        │
┌─────────┴─┐                               ┌──────────┐
│   auth    │                               │  api     │
└─────────┬─┘                               └──────────┘
          │                                        ▲
          │         ↓ expectation: "Session ID"    │
          │         ↓ promise: "Session manager"   │
          │                                        │
          └────────────────────────────────────────┘
                                         ┌──────────┐
                                         │ websocket│
                                         └──────────┘
```

## Error Cases

| Error | Cause | Solution |
|-------|-------|----------|
| `Node <id> not found` | Target doesn't exist | Create node first |
| `Dependency <id> not found` | Dependency doesn't exist | Create dependency first |
| `Edge already exists` | Already connected | Use edit-node to update |
| `Would create cycle` | Would form circular dependency | Restructure graph |

