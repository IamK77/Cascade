# inspect

Read-only review of a task. Shows the briefing a worker would see (upstream context, promises, downstream topology) plus the node's own delivered context if completed. No side effects.

## Usage

```bash
cascade inspect --task <task-id>
```

## Parameters

| Parameter | Short | Required | Description |
|-----------|-------|----------|-------------|
| `--task` | `-t` | Yes | Task ID to inspect |

## Output

Markdown briefing identical to what `cascade get-task` produces, with two additions:

- `_State: <STATE>_` line under the briefing
- `## Delivered` section showing `summary` / `critical` / `artifacts` if the node is COMPLETED

## When to use

- **Before dispatching a worker**: verify upstream context contains what the worker needs. If the briefing is thin, enrich upstream artifacts before dispatch.
- **After completion**: review what the worker delivered. Compare against the node's promises to downstream — if delivery is inadequate, use `rework` before dispatching the next wave.

## Distinction from `get-task`

`inspect` is read-only. `get-task` claims the task (state → ACTIVE) and is meant for workers, not orchestrators.
