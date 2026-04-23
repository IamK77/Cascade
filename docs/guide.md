# Cascade Guide

From building your first task graph to running a multi-agent workflow with dynamic editing.

## 1. Setup

```bash
uv sync
```

## 2. Build a Task Graph

Every workflow starts with a DAG. Nodes are tasks, edges are dependencies with contracts.

```python
from cascade import GraphStorage
from tools import add_node

storage = GraphStorage(".cascade")

# Root task — no dependencies, starts as READY
add_node(storage, {"node_id": "analyze"})

# Dependent task — needs a contract on the edge
add_node(storage, {
    "node_id": "design",
    "dependencies": ["analyze"],
    "expectations": [{
        "node_id": "analyze",
        "expectation": "Feature requirements and constraints",
        "promise": "Deliver prioritized feature list",
    }],
})

# Chain continues
add_node(storage, {
    "node_id": "implement",
    "dependencies": ["design"],
    "expectations": [{
        "node_id": "design",
        "expectation": "API specification with endpoints",
        "promise": "Deliver endpoint designs",
    }],
})
```

**Maximize parallelism** — split horizontally wherever possible:

```python
add_node(storage, {"node_id": "fix_frontend_bugs"})
add_node(storage, {"node_id": "refactor_backend"})
# Independent tasks run in parallel — no connection needed
```

## 3. Claim and Complete Tasks

```python
from tools import get_task, finish_task

# Agent claims the highest-priority READY task (critical path first)
result = get_task(storage, {"agent_id": "agent-001"})
task_info = result["data"]["task_info"]

# task_info contains:
# - upstream: each ancestor with contract + delivered context
# - promises: what you owe to downstream
# - visible_nodes: preview of downstream topology

# Complete with output that flows downstream
finish_task(storage, {
    "task_id": "analyze",
    "success": True,
    "summary": "Requirements: JWT auth + REST API for users and posts",
    "critical": {
        "auth_type": "JWT",
        "endpoints": ["/users", "/posts"],
        "database": "PostgreSQL",
    },
})
```

### Upstream View

When you claim a task, you see each ancestor's contribution separately:

```json
{
  "upstream": [
    {
      "node_id": "analyze",
      "state": "COMPLETED",
      "distance": 1,
      "path": ["analyze"],
      "expectation": "Feature requirements and constraints",
      "promise": "Deliver prioritized feature list",
      "delivered": {
        "summary": "Requirements: JWT auth + REST API",
        "critical": {"auth_type": "JWT", "database": "PostgreSQL"}
      }
    }
  ]
}
```

- **distance 1** (direct parents): includes contract (expectation/promise)
- **distance 2+** (grandparents): includes path for provenance, no contract
- Fan-in: each source is separate — no key overwrite

### Context Channels

Your output flows downstream through three channels:

| Channel | Use for | Propagation |
|---------|---------|-------------|
| `summary` | Brief text of what you did | Children + grandchildren (2 hops) |
| `critical` | Structured KV data downstream tasks need | All descendants (infinite) |
| `artifacts` | Full documents, code, specs | All descendants (file reference) |

**Rule of thumb**: if downstream agents need to _use_ it programmatically, put it in `critical`. If they need to _read_ it, `summary`. If it's a full document, `artifacts`.

### Contract Semantics

- **expectation**: what the downstream node needs — consumer's perspective
- **promise**: what the upstream node delivers — producer's perspective

The framework warns if multiple edges to the same node have identical promises.

## 4. Dynamic Editing

The initial DAG is a starting hypothesis. The orchestrator monitors and adapts.

### Split — break a big task into smaller ones

```python
from tools import split_node

# ACTIVE nodes must be released first
split_node(storage, {
    "parent_id": "implement",
    "new_nodes": [{"node_id": "impl_auth"}, {"node_id": "impl_api"}],
    "reason": "Task too large for one agent",
})
# implement removed, new nodes inherit its dependencies and dependents
```

### Refine — add a missing dependency

```python
from tools import refine_node

refine_node(storage, {
    "node_id": "impl_api",
    "dependency_id": "design_schema",
    "expectation": "Database schema for CRUD operations",
    "promise": "PostgreSQL schema with migrations",
    "reason": "Discovered hidden dependency during implementation",
})
# impl_api goes PENDING if design_schema isn't completed yet
```

### Rework — upstream output was wrong

```python
from tools.rework import rework

rework(storage, {
    "source_node_id": "analyze",
    "corrective_node_id": "analyze_oauth",
    "reason": "Missing OAuth2 requirements for Google/GitHub login",
    "agent_id": "agent-002",
    "source_expectation": "Original analysis to review",
    "source_promise": "First analysis output",
    "corrective_expectation": "Revised requirements with OAuth2",
    "corrective_promise": "Updated auth requirements",
})
# Graph grows forward — no reverse edges
# Agent's task goes PENDING until corrective work completes
```

### Remove — cancel unnecessary tasks

```python
from tools import remove_node

# ACTIVE nodes cannot be removed — release first
remove_node(storage, {
    "node_id": "deprecated_module",
    "cascade": True,          # also remove all dependents
    "reason": "No longer needed after architecture change",
})
```

All mutation tools support `reason` — recorded in the event log for audit.

## 5. Cancellation

Two implementations of the same semantic:

### Cross-process (file-based)

```python
from tools import check_task

# Pull: check if a task claim is still valid
result = check_task(storage, {"task_id": "analyze"})
# {"valid": true, "agent_id": "agent-001", ...}
```

### In-process (memory-based)

```python
from cascade.context.cancellation import CancellationToken

token = CancellationToken()
get_task(storage, {
    "agent_id": "agent-001",
    "task_id": "analyze",
    "cancel_notifier": token,  # CancellationToken IS a CancelNotifier
})

# In another coroutine/thread — when task is released/reworked/timed out:
# token.is_cancelled becomes True, registered callbacks fire instantly
```

### Push notifications

```python
from cascade.storage.token_store import FileNotifier

get_task(storage, {
    "agent_id": "agent-001",
    "task_id": "analyze",
    "cancel_notifier": FileNotifier("/tmp/agent-001.cancel"),
})
# When task is invalidated, framework writes to that file
# Implement CancelNotifier protocol for webhook, Redis, etc.
```

## 6. Multi-Agent Coordination

Multiple agents share the same `.cascade/` directory. File locking ensures consistency.

```python
# Terminal 1                          # Terminal 2
get_task(s, {"agent_id": "agent-1"})  get_task(s, {"agent_id": "agent-2"})
# → claims analyze                    # → claims design (if ready)
```

- **One task per agent** — `get_task` with an active task returns a reminder
- **Critical path priority** — longest downstream chain is scheduled first
- **ACTIVE protection** — cannot remove/split a node with an active agent
- **Timeouts** — auto-release stalled tasks:

```python
get_task(storage, {"agent_id": "agent-1", "timeout": 3600})  # 1 hour

from tools.check_timeouts import check_timeouts
check_timeouts(storage, {"default_timeout": 1800})  # release stalled > 30min
```

## 7. Monitoring

### List tasks

```python
from tools import list_nodes
list_nodes(storage, {})                          # all
list_nodes(storage, {"state_filter": "READY"})   # only ready
```

### Event history

```python
from tools.history import history
history(storage, {"summary": True})              # counts by type
history(storage, {"node_id": "analyze"})         # one node's events
history(storage, {"last_n": 10})                 # last 10
```

## 8. Error Recovery

```python
# Release — give up temporarily, task returns to READY
finish_task(storage, {"task_id": "build", "release": True, "summary": "Blocked"})

# Fail — task cannot be completed, downstream stays PENDING
finish_task(storage, {"task_id": "deploy", "success": False, "summary": "Error"})

# Cascade fail — abort entire downstream chain
finish_task(storage, {"task_id": "core", "success": False, "cascade": True})
```

## 9. Framework Integration

Tools are `(GraphStorage, dict) → dict`. Wrap for any framework:

```python
from cascade import GraphStorage
from tools import get_task, finish_task

storage = GraphStorage(".cascade")

# Anthropic tool_use example
tools = [{
    "name": "claim_task",
    "input_schema": {
        "type": "object",
        "properties": {
            "agent_id": {"type": "string"},
            "task_id": {"type": "string"},
        },
        "required": ["agent_id"],
    },
}]

def handle_tool(name, input):
    if name == "claim_task":
        return get_task(storage, input)
```

## CLI Reference

```bash
cascade add-node --id <id> [--deps <ids>] [--expectations '<json>']
cascade get-task --agent <id> [--task <id>] [--timeout <sec>]
cascade finish-task --task <id> --success [--summary <text>] [--critical '<json>']
cascade finish-task --task <id> --fail [--reason <text>] [--cascade]
cascade finish-task --task <id> --release [--reason <text>]
cascade split-node --parent <id> --children <id1,id2> [--reason <text>]
cascade refine-node --node <id> --dep <id> --expectation <text> --promise <text> [--reason <text>]
cascade remove-node --node <id> [--cascade] [--reason <text>]
cascade edit-node --node <id> [--state <state>] [--critical '<json>'] [--context-merge replace|merge|append] [--reason <text>]
cascade rework --source <id> --corrective <id> --reason <text> --agent <id>
cascade check-task --task <id>
cascade check-timeouts [--default-timeout <sec>]
cascade history [--node <id>] [--type <type>] [--last <n>] [--summary]
cascade list-nodes [--state <state>]
```
