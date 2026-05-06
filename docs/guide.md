# Cascade Guide

From building your first task graph to running a multi-agent workflow with dynamic editing.

## 1. Setup

```bash
pip install cascade-auto
```

Or for development:

```bash
git clone https://github.com/autoseek-ai/Cascade.git
cd Cascade
uv sync
```

## 2. Build a Task Graph

Every workflow starts with a DAG. Nodes are tasks, edges are dependencies with contracts.

```python
from cascade import CascadeClient, Contract

cascade = CascadeClient()

# Root task — no dependencies, starts as READY
cascade.add("analyze")

# Dependent task — needs a contract on the edge
cascade.add("design", deps={
    "analyze": Contract(
        "Feature requirements and constraints",
        "Deliver prioritized feature list",
    ),
})

# Chain continues
cascade.add("implement", deps={
    "design": Contract(
        "API specification with endpoints",
        "Deliver endpoint designs",
    ),
})
```

**Maximize parallelism** — split horizontally wherever possible:

```python
cascade.add("fix_frontend_bugs")
cascade.add("refactor_backend")
# Independent tasks run in parallel — no connection needed
```

## 3. Claim and Complete Tasks

```python
from cascade.types import TaskView

# Agent claims the highest-priority READY task (critical path first)
r = cascade.claim("agent-001")
# r is a Result — check r.success, r.data["task_id"], etc.

# For typed access to upstream context and promises:
task = TaskView.from_result(r)
# task.id, task.upstream, task.promises, task.token

# Complete with output that flows downstream
cascade.complete("analyze",
    summary="Requirements: JWT auth + REST API for users and posts",
    critical={
        "auth_type": "JWT",
        "endpoints": ["/users", "/posts"],
        "database": "PostgreSQL",
    },
)
# Framework auto-injects produced_at and git_ref into critical
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
        "critical": {
          "auth_type": "JWT",
          "database": "PostgreSQL",
          "produced_at": 1778050765.98,
          "git_ref": "a3f8c2e..."
        }
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

### Context Freshness

On `complete()`, the framework automatically injects provenance metadata into `critical`:

| Key | Value | Present |
|-----|-------|---------|
| `produced_at` | Unix timestamp of completion | Always |
| `git_ref` | HEAD commit hash at completion time | Only inside a git repo |

The view layer renders a human-readable **Freshness** line in task briefings:

```
- **Freshness**: 2h 15m ago | 3 commits behind HEAD
```

Downstream agents can use `git_ref` to run `git diff {git_ref}..HEAD` and assess whether upstream context is still relevant. Outside a git repo, only the timestamp dimension is available.

### Contract Semantics

- **expectation**: what the downstream node needs — consumer's perspective
- **promise**: what the upstream node delivers — producer's perspective

The framework warns if multiple edges to the same node have identical promises.

## 4. Dynamic Editing

The initial DAG is a starting hypothesis. The orchestrator monitors and adapts.

### Split — break a big task into smaller ones

```python
# ACTIVE nodes must be released first
cascade.split("implement",
    children=["impl_auth", "impl_api"],
    reason="Task too large for one agent",
)
# implement removed, new nodes inherit its dependencies and dependents
```

### Refine — add a missing dependency

```python
cascade.refine("impl_api",
    dep="design_schema",
    expectation="Database schema for CRUD operations",
    promise="PostgreSQL schema with migrations",
    reason="Discovered hidden dependency during implementation",
)
# impl_api goes PENDING if design_schema isn't completed yet
```

### Rework — upstream output was wrong

```python
cascade.rework(
    source="analyze",
    corrective="analyze_oauth",
    reason="Missing OAuth2 requirements for Google/GitHub login",
    agent_id="agent-002",
    source_expectation="Original analysis to review",
    source_promise="First analysis output",
    corrective_expectation="Revised requirements with OAuth2",
    corrective_promise="Updated auth requirements",
)
# Graph grows forward — no reverse edges
# Agent's task goes PENDING until corrective work completes
```

### Remove — cancel unnecessary tasks

```python
# ACTIVE nodes cannot be removed — release first
cascade.remove("deprecated_module",
    cascade=True,
    reason="No longer needed after architecture change",
)
```

All mutation tools support `reason` — recorded in the event log for audit.

## 5. Cancellation

### Cross-process (file-based) — the common pattern

```python
# Pull: check if a task claim is still valid
result = cascade.check("analyze")
# {"valid": true, "agent_id": "agent-001", ...}
```

When a task is released, reworked, or timed out, `cascade.check()` reflects the new state. Agents should poll periodically during long-running work.

### In-process (memory-based) — advanced

For direct framework embedding, `CancellationToken` provides instant push notifications within a single process:

```python
from cascade.context.cancellation import CancellationToken

token = CancellationToken()
# Pass token when claiming via the lower-level tool API
# token.is_cancelled becomes True when task is invalidated
# Registered callbacks fire instantly
```

Implement the `CancelNotifier` protocol for custom push mechanisms (webhook, Redis, etc.).

## 6. Multi-Agent Coordination

Multiple agents share the same `.cascade/` directory. File locking ensures consistency.

```python
# Agent 1                              # Agent 2
cascade.claim("agent-1")               cascade.claim("agent-2")
# → claims analyze                     # → claims design (if ready)
```

- **One task per agent** — `claim` with an active task returns a reminder
- **Critical path priority** — longest downstream chain is scheduled first
- **ACTIVE protection** — cannot remove/split a node with an active agent
- **Timeouts** — auto-release stalled tasks:

```python
cascade.claim("agent-1", task_id="analyze", timeout=3600)  # 1 hour

cascade.check_timeouts(default_timeout=1800)  # release stalled > 30min
```

## 7. Monitoring

### List tasks

```python
from cascade.types import NodeInfo

r = cascade.nodes()                         # Result with all nodes
r = cascade.nodes(state="READY")            # filter by state
nodes = NodeInfo.list_from_result(r)        # typed projection
```

### Event history

```python
cascade.history(summary=True)         # counts by type
cascade.history(node_id="analyze")    # one node's events
cascade.history(last_n=10)            # last 10
```

## 8. Error Recovery

```python
# Release — give up temporarily, task returns to READY
cascade.release("build", reason="Blocked on external dependency")

# Fail — task cannot be completed, downstream stays PENDING
cascade.fail("deploy", reason="Deployment target unavailable")

# Cascade fail — abort entire downstream chain
cascade.fail("core", cascade=True, reason="Critical failure in core module")
```

## 9. Framework Integration

`CascadeClient` is the primary API for all Cascade operations. All methods return `Result`. For LLM framework integration (Anthropic tool_use, OpenAI function calling, etc.), the underlying `(StorageProtocol, dict) -> dict` tool layer provides a dict-based serialization boundary:

```python
from cascade import CascadeClient, Contract, FileStorage
from cascade.types import TaskView

# Primary API — use this for application code
cascade = CascadeClient()
cascade.add("analyze")
r = cascade.claim("agent-001")
task = TaskView.from_result(r)

# Lower-level tool layer — for framework integration
from tools.get_task import get_task

storage = FileStorage(".cascade")

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
