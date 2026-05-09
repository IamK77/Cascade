# watch

Stream node state transitions to stdout as JSONL. Long-running command — stays alive until terminated, emits one line per state change. **Edge-triggered**: only state changes produce output, idle DAGs are silent.

## Usage

```bash
cascade watch
```

Press Ctrl-C to exit.

## Output format

One JSON object per line:

```json
{"type":"transition","node":"analyze","from":null,"to":"READY","ts":1777400000.1}
{"type":"transition","node":"analyze","from":"READY","to":"ACTIVE","agent":"worker-1","ts":1777400005.3}
{"type":"transition","node":"analyze","from":"ACTIVE","to":"COMPLETED","ts":1777400060.7}
{"type":"transition","node":"design","from":"PENDING","to":"READY","ts":1777400060.7}
```

Fields:
- `node` — node ID
- `from` — previous state, or `null` for newly added nodes
- `to` — new state, or `null` for removed nodes
- `agent` — present on `READY → ACTIVE` (the claiming worker)
- `ts` — Unix timestamp

## How it works

Watches `.cascade/graph.json` for changes via mtime polling (~50ms granularity). On every change, diffs the new state against the last seen snapshot and emits a transition per node whose `state` field changed.

The initial read at startup is the baseline — no transitions emitted for nodes that already exist. Only changes after watch starts.

## When to use

Pair with an agent harness's monitoring tool (e.g. Claude Code's Monitor) to drive orchestrator reactions:

- `from:null, to:READY` — new node ready, dispatch a worker
- `from:PENDING, to:READY` — upstream completed, downstream is now ready
- `from:ACTIVE, to:COMPLETED` — worker delivered, review the output
- `from:ACTIVE, to:FAILED` — worker failed, decide next step

## vs polling list-nodes

Don't poll `cascade list-nodes` to detect changes — it re-emits the same set every interval, regardless of change. Watch is silent when idle and emits exactly once per transition.

## Implementation note

Watch reads `graph.json` directly without acquiring the cascade lock. Saves are atomic (tmp + rename), so a reader sees either the old or new file complete — never a torn write.
