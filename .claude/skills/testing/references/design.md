# Test Design Reference

## Case Format

```
GIVEN  [precondition / system state]
WHEN   [action or input]
THEN   [expected outcome]
```

Minimum per function: one happy path, one error path, relevant boundaries.

## Boundary Identification

| Domain | Boundaries to test |
|---|---|
| Numeric | `min-1`, `min`, `min+1`, `max-1`, `max`, `max+1` |
| String | `""`, `" "`, single char, max-length, max+1, `\n`/`\0`, emoji, non-ASCII |
| Collection | `[]`, `[x]`, `[x,x]` (duplicates), sorted, reverse-sorted, at-capacity, over-capacity |
| State machine | every valid transition; every transition that should be rejected |
| Time / dates | leap day (Feb 29), year rollover (Dec 31→Jan 1), DST, token expired at exactly `now` |
| Concurrency | simultaneous writes to same resource, double-submit, last-write-wins race |
| File system | empty file, file at size limit, missing file, locked file, corrupted content, truncated write |
| Network | timeout threshold, max retries, partial/truncated response |
| Auth | just-granted, just-revoked, expired at boundary (now-1s / now+1s), conflicting roles |

## Domain-Specific Invariants (for property-based testing)

### Generic invariants (starting point)
- **Roundtrip**: `decode(encode(x)) == x`
- **Idempotency**: `f(f(x)) == f(x)`
- **Commutativity**: `f(a,b) == f(b,a)`
- **Monotonicity**: `a <= b → f(a) <= f(b)`
- **No-crash**: valid-typed input never throws unhandled exception

### How to find domain-specific invariants
1. Read the system's state machine / transition rules
2. Read the architecture doc or CLAUDE.md for stated principles
3. Ask: **"What must ALWAYS be true, no matter what sequence of operations?"**

### Real examples
- "Terminal nodes never have agent_id set" — found a bug where `fail()` didn't clear `claimed_at`
- "Replay of events produces identical graph to direct operations" — found handlers contradicting state machine
- "Graph is acyclic after any sequence of edge additions" — validates cycle detection
- "Node readiness always matches dependency state" — catches stale readiness computations

Cross-component invariants are where property testing finds real bugs.

## Regression Test Rule

A regression test must **fail on the unfixed code** and **pass after the fix**. If it passes both ways, it's not testing the bug.

## Framework Reference

| Language | Unit | Property-Based | E2E | Fuzz |
|---|---|---|---|---|
| Python | `pytest` | `hypothesis` | `playwright` | `atheris` |
| JS / TS | `jest` / `vitest` | `fast-check` | `playwright` / `cypress` | `jsfuzz` |
| Java | `JUnit 5` | `jqwik` | `Selenium` | `jazzer` |
| Go | `testing` | `rapid` | — | `go-fuzz` |
| Rust | `#[test]` | `proptest` | — | `cargo-fuzz` |

## Code Quality Rules
- One logical assertion per test
- Test names describe the scenario: `test_fail_clears_claimed_at_and_timeout`
- No control flow (`if`, `for`) inside tests — parameterize instead
- Mock at the boundary of the unit, not deep inside it
