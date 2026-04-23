# Context System

Context is how tasks pass information downstream. When a task completes, its context is available to dependents — each upstream contribution is kept separate with full provenance (node_id, path, distance).

## Three Context Channels

| Channel | Use For | Propagation | At Fan-In |
|---------|---------|-------------|-----------|
| `critical` | Structured decisions, configs | Indefinitely | Separate per source |
| `summary` | Brief text descriptions | 2 hops (children + grandchildren) | Separate per source |
| `artifacts` | Detailed docs, code, schemas | Indefinitely (file ref) | Separate per source |

## critical (Key-Value Pairs)

**Use for**: structured data that downstream tasks need to make decisions.

```bash
cascade finish-task --task analyze --success \
  --critical '{
    "framework": "Next.js",
    "database": "PostgreSQL",
    "api_style": "REST"
  }'
```

- Propagates to ALL descendants indefinitely
- At fan-in nodes, each parent's critical data is kept separate (no key conflicts)

## summary (Text)

**Use for**: human-readable descriptions of what was accomplished.

```bash
cascade finish-task --task analyze --success \
  --summary "Analyzed requirements: need OAuth2 + email auth"
```

- Propagates to children and grandchildren only (distance ≤ 2)
- Each parent's summary is a separate entry, not concatenated

## artifacts (Detailed Content)

**Use for**: full documents, code, schemas, specs.

```bash
cascade finish-task --task design --success \
  --artifacts "# API Design\n\n## Endpoints\n\nPOST /auth/login\n..."
```

- Persisted to `.cascade/artifacts/<node_id>.md`
- File reference propagates indefinitely

## Receiving Context

When you `get-task`, you receive an **upstream** list — each entry is one ancestor node with its contract (if direct parent) and delivered context:

```json
{
  "upstream": [
    {
      "node_id": "requirements",
      "state": "COMPLETED",
      "distance": 1,
      "path": ["requirements"],
      "expectation": "Need tech stack decisions",
      "promise": "Provide requirements analysis",
      "delivered": {
        "summary": "Need OAuth2 + email auth",
        "critical": {"framework": "Next.js"}
      }
    },
    {
      "node_id": "root-analysis",
      "state": "COMPLETED",
      "distance": 2,
      "path": ["root-analysis", "requirements"],
      "delivered": {
        "critical": {"project_type": "e-commerce"}
      }
    }
  ]
}
```

- **distance 1** (direct parents): includes `expectation` and `promise` from the edge contract
- **distance 2+** (grandparents): includes `path` for provenance, no contract (no direct edge)
- No data is merged or overwritten — each source is separate

## Context Auto-Creation

If a node has no context when you call `finish-task`, one is created automatically. Your output is **never silently dropped**.

## Best Practices

| Scenario | Channel |
|----------|---------|
| Tech stack decisions | `critical` |
| API endpoints list | `critical` |
| Version numbers | `critical` |
| Task completion description | `summary` |
| Decision rationale | `summary` |
| Full API specification | `artifacts` |
| Database schema | `artifacts` |
| Code templates | `artifacts` |
