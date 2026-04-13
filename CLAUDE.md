# Cascade

DAG-based multi-agent task scheduling framework. Agents claim tasks from a
dependency graph, pass context through edges, and coordinate via contracts.
Event sourcing provides a complete audit trail.

## Test Command

```
uv run pytest tests/
```

## Module Structure

```
types -> core -> context -> view -> operations -> tools
```

| Package      | Description                                              |
|------------- |----------------------------------------------------------|
| `types`      | Value types (Contract, Context, EdgeId) - no internal deps |
| `core`       | Cascade graph, Node, NodeState with transition rules     |
| `context`    | Context propagation + cancellation (Go-style tokens)     |
| `view`       | Presentation layer for agent task views                  |
| `operations` | Split, Remove, Rework operations with base class         |
| `storage`    | JSON persistence with fcntl file locking + EventStore    |

## State Machine

`PENDING -> READY -> ACTIVE -> COMPLETED`
Also: `ACTIVE -> READY` (release), any state `-> CANCELLED / FAILED`

## Architecture Principles

- **Mandatory contracts** on every edge between nodes
- **Computed readiness** — never cached, always derived from dependencies
- **Forward-only rework** — new corrective nodes, never mutate parent
- **Event sourcing** — append-only JSONL log for all state changes
- **Critical-path scheduling** via downstream depth
- **Go-style cancellation tokens** for cooperative cancellation
- **3-tier context propagation** (critical / summary / artifacts)

## Tool Inventory

| Tool              | Purpose                          |
|-------------------|----------------------------------|
| `add_node`        | Add a task node to the graph     |
| `remove_node`     | Remove a node from the graph     |
| `split_node`      | Split a node into sub-tasks      |
| `refine_node`     | Refine a node's specification    |
| `edit_node`       | Edit node properties             |
| `get_task`        | Claim/retrieve a task for agent  |
| `finish_task`     | Mark a task as completed         |
| `rework`          | Create corrective rework nodes   |
| `check_timeouts`  | Check for timed-out tasks        |
| `list_nodes`      | List all nodes in the graph      |
| `history`         | View event sourcing history      |

## Key Types

`Contract`, `Context`, `ContextLevel`, `Node`, `NodeState`, `EdgeId`,
`CancellationToken`, `OperationResult`
