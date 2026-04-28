# add-nodes

Atomically add multiple task nodes in a single lock acquisition. Use this instead of repeated `add-node` calls when building a DAG with many nodes — one shell invocation, one validation pass, one persisted graph save.

## Usage

```bash
cascade add-nodes --json '<JSON array>'
cascade add-nodes --file <path-to-json>
```

## Parameters

| Parameter | Short | Required | Description |
|-----------|-------|----------|-------------|
| `--json` | — | One of | Inline JSON array of node specs |
| `--file` | `-f` | One of | Path to a JSON file with node specs |

## JSON shape

```json
[
  {"id": "analyze"},
  {
    "id": "models",
    "deps": ["analyze"],
    "expectations": [
      {"node_id": "analyze", "expectation": "Need data shapes", "promise": "Deliver field definitions"}
    ]
  },
  {
    "id": "ops",
    "deps": ["models"],
    "expectations": [
      {"node_id": "models", "expectation": "Need models", "promise": "Deliver Python dataclasses"}
    ]
  }
]
```

Each item supports the same fields as `add-node`: `id`, `deps`, `dependents`, `expectations`. Order matters — a spec can reference deps from earlier specs in the same batch.

## Atomicity

If any spec fails (duplicate id, missing dependency, malformed contract), **no nodes are added** and no events are emitted. The whole batch is rejected.

## Why batch

Sub-agent dispatch incurs per-call validation overhead (e.g., shell command pre-flight checks). Building a 10-node DAG with 10 separate `add-node` invocations multiplies this overhead. `add-nodes` consolidates the dispatch, lock acquisition, validation, and graph save into a single operation.
