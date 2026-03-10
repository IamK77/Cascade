# Cascade Usage Guide

Cascade is a DAG-based task scheduling framework designed for LLM agents. It provides a CLI, Python API, and framework-agnostic tool functions.

## Installation

```bash
pip install cascade
# or
uv add cascade
```

## CLI Usage

```bash
# Add tasks
cascade add-node --id analyze
cascade add-node --id design --deps analyze
cascade add-node --id implement --deps design

# Get task
cascade get-task --agent agent-001

# Complete with context
cascade finish-task --task analyze --success \
    --summary "Requirements analyzed" \
    --critical '{"features": ["auth", "api"]}'

# List tasks
cascade list-nodes
```

### CLI Commands

| Command | Description |
|---------|-------------|
| `add-node` | Create a new task |
| `get-task` | Claim a task to work on |
| `finish-task` | Complete, fail, or release a task |
| `list-nodes` | View all tasks and their states |
| `split-node` | Break down a complex task |
| `refine-node` | Add a dependency to a task |
| `remove-node` | Delete a task |
| `edit-node` | Update task properties |

### add-node

```bash
# Basic
cascade add-node --id task_1

# With dependencies
cascade add-node --id task_2 --deps task_1

# With contract on edge
cascade add-node --id task_2 --deps task_1 \
    --expectations '[{"node_id": "task_1", "expectation": "...", "promise": "..."}]'

# That existing nodes depend on
cascade add-node --id common --dependents task_a,task_b
```

### get-task

```bash
# Get any available task
cascade get-task --agent agent-001

# Get specific task
cascade get-task --agent agent-001 --task implement
```

Returns `task_info`:
```json
{
  "id": "implement",
  "state": "ACTIVE",
  "context": {
    "critical": {"features": ["auth"]},
    "summary": "Upstream summary..."
  },
  "contracts": [{"node_id": "design", "promise": "API spec"}],
  "promises": [{"to_node": "test", "promise": "Working code"}],
  "visible_nodes": {"1": [...], "2": [...]}
}
```

### finish-task

```bash
# Complete
cascade finish-task --task analyze --success \
    --summary "Done" \
    --critical '{"key": "value"}'

# Fail
cascade finish-task --task deploy --fail --reason "Timeout"

# Fail and cascade to dependents
cascade finish-task --task build --fail --cascade

# Release back to READY
cascade finish-task --task implement --release --reason "Need info"
```

### list-nodes

```bash
cascade list-nodes
cascade list-nodes --state READY
cascade list-nodes --state PENDING
```

## Python API

```python
from cascade import GraphStorage, add_node, get_task, finish_task, list_nodes

storage = GraphStorage(".cascade")

# Add tasks
add_node(storage, {"node_id": "analyze"})
add_node(storage, {"node_id": "design", "dependencies": ["analyze"]})

# Get task
task = get_task(storage, {"agent_id": "agent-001"})

# Complete
finish_task(storage, {
    "task_id": "analyze",
    "success": True,
    "summary": "Requirements analyzed",
    "critical": {"features": ["auth", "api"]}
})

# List
nodes = list_nodes(storage, {"state_filter": "READY"})
```

## Framework Integration

Cascade is framework-agnostic. Wrap the tools for your agent framework:

```python
from cascade import GraphStorage, add_node, get_task, finish_task

storage = GraphStorage(".cascade")

# Your framework's tool definition
@tool
def create_task(node_id: str, dependencies: list = None):
    """Add a new task to the DAG."""
    return add_node(storage, {
        "node_id": node_id,
        "dependencies": dependencies or []
    })

@tool
def take_task(agent_id: str, task_id: str = None):
    """Get a task to work on."""
    params = {"agent_id": agent_id}
    if task_id:
        params["task_id"] = task_id
    return get_task(storage, params)

@tool
def complete_task(task_id: str, success: bool = True, summary: str = None):
    """Mark task as complete or failed."""
    params = {"task_id": task_id, "success": success}
    if summary:
        params["summary"] = summary
    return finish_task(storage, params)
```

## Core Concepts

### Node States

```
PENDING → READY → ACTIVE → COMPLETED/FAILED/CANCELLED
```

### Contracts on Edges

Expectation/promise is stored on **edges**, allowing different promises to different downstream tasks:

```python
add_node(storage, {
    "node_id": "task_b",
    "dependencies": ["task_a"],
    "expectations": [{
        "node_id": "task_a",
        "expectation": "Need config",
        "promise": "Config output"
    }]
})
```

### Context Propagation

Context from completed tasks is **merged** and propagated downstream:
- `critical`: Key-value pairs (latest wins)
- `summary`: Text concatenated
- `artifacts`: Detailed output

## Rules

1. **No isolated nodes**: Only the first task can have no dependencies
2. **One task per agent**: An agent can only hold one ACTIVE task
3. **Contracts on edges**: Expectation/promise is per-edge, not per-node
