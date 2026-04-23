# rework

Request corrective work when an upstream node's output is inadequate. Creates a corrective node that grows the graph forward — no reverse edges.

## Usage

```bash
cascade rework --source <source-id> --corrective <new-id> --reason <why> --agent <agent-id> [contracts]
```

## Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `--source` | Yes | The upstream COMPLETED node whose output needs correction |
| `--corrective` | Yes | ID for the new corrective node |
| `--reason` | Yes | Why rework is needed (becomes corrective node's context) |
| `--agent` | Yes | Agent requesting rework (must own an ACTIVE task) |
| `--source-expectation` | Yes | What corrective node expects from original source |
| `--source-promise` | Yes | What source promises (its original output) |
| `--corrective-expectation` | Yes | What requesting node expects from correction |
| `--corrective-promise` | Yes | What corrective node promises to deliver |

## What Happens

1. Corrective node created with `reason` as context
2. Edge: source → corrective (corrective agent sees original output)
3. Edge: corrective → your task (you wait for correction)
4. Your task: ACTIVE → PENDING (released, waiting for correction)
5. Your agent assignment cleared

```
Before:  A(COMPLETED) → B(ACTIVE, you discover problem)

After:   A(COMPLETED) → A'(READY, corrective) → B(PENDING, waiting)
         A(COMPLETED) → B(PENDING)
```

## Example

```bash
# You're working on implement, discover design missed OAuth
cascade rework \
  --source design \
  --corrective design-oauth \
  --reason "Missing OAuth2 requirements for Google/GitHub login" \
  --agent agent-2 \
  --source-expectation "Original design to review" \
  --source-promise "First design output" \
  --corrective-expectation "Revised design with OAuth2 flows" \
  --corrective-promise "Updated design spec"

# Result:
# - design-oauth created (READY, depends on design)
# - Your task goes PENDING (waits for design-oauth)
# - Another agent picks up design-oauth, completes it
# - Your task becomes READY again with corrected context
```

## See Also

- [concepts.md](../concepts.md) — Rework section
- [finish-task.md](finish-task.md) — Release as alternative
