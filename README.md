# Cascade

A cascade-based collaboration framework for multi-agent systems.

## Features

- **DAG Task Scheduling**: Tasks with dependencies, automatic state transitions
- **Context Propagation**: Three-level context system (Critical, Summary, Artifacts) flows downstream
- **Contract System**: Expectation/promise contracts stored on edges for flexible task relationships
- **Multi-Agent Coordination**: Agent tracking, one task per agent
- **Cascade Cancellation**: Go-style context cancellation propagation
- **Persistence**: File-based storage with locking for concurrent access

## Installation

```bash
uv sync
```

## Quick Start

```python
from cascade import Cascade, Node, NodeState, GraphStorage

# Create storage
storage = GraphStorage(".cascade")

# Create nodes and build graph
storage.load() or Cascade()

# Add tasks with dependencies
from cascade import add_node, get_task, finish_task

add_node(storage, {"node_id": "analyze"})
add_node(storage, {"node_id": "design", "dependencies": ["analyze"]})
add_node(storage, {"node_id": "implement", "dependencies": ["design"]})

# Get and complete a task
task = get_task(storage, {"agent_id": "agent-001"})
finish_task(storage, {
    "task_id": "analyze",
    "success": True,
    "summary": "Requirements analyzed",
    "critical": {"features": ["auth", "api"]}
})
```

## Core Concepts

### Node States

```
PENDING → READY → ACTIVE → COMPLETED/FAILED/CANCELLED
```

### Context Propagation

Context from completed tasks is **merged** and propagated to downstream tasks:
- `critical`: Key-value pairs (latest wins on conflict)
- `summary`: Text summaries concatenated
- `artifacts`: Detailed output

### Contracts on Edges

Expectation/promise is stored on **edges**, allowing different promises to different downstream tasks:

```python
add_node(storage, {
    "node_id": "task_b",
    "dependencies": ["task_a"],
    "expectations": [{
        "node_id": "task_a",
        "expectation": "Expect config",
        "promise": "A promises config output"
    }]
})
```

## Documentation

See [docs/usage.md](docs/usage.md) for detailed usage guide.

## License

Apache-2.0
