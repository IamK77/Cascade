---
name: testing
description: >
  Systematically design, generate, and review tests for software projects.
  Trigger when the user mentions testing, wants to write tests, asks how to test
  a function/module/API, mentions unit tests, integration tests, edge cases,
  property-based testing, coverage, or says things like "help me test this",
  "what should I test", "write tests for this code", "I just fixed a bug".
---

# Software Testing

Testing is a collaboration between you and the user. You bring systematic coverage; the user brings domain knowledge and judgment calls. Neither works well alone.

Every phase below has a **checkpoint** — a moment where you must pause and interact with the user before proceeding. Do not skip checkpoints. They exist because the user's input at these moments changes the direction of work.

---

## Phase 0: Understand the Motivation

Before anything else, understand **why** the user wants tests.

| Motivation | Strategy |
|---|---|
| "I fixed a bug" | Regression test — reproduce the exact failure |
| "I'm refactoring" | High unit coverage as a safety net |
| "I want to find unknown bugs" | Property-based, chaos, cross-component invariants |
| "I'm going to prod soon" | Smoke + E2E critical paths |
| "The system crashes under load" | Stress, chaos, concurrent contention |
| "I want general confidence" | Start with reconnaissance, then decide |

**CHECKPOINT (PREFLIGHT 1/6):** If the motivation is unclear, ask: **"What's prompting this — a bug, a refactor, a release, or just general confidence?"** Do not proceed until you know.

---

## Phase 1: Reconnaissance

**Do not write tests yet.** First understand what exists and where the gaps are.

### 1.1 Run coverage

```bash
pytest --cov=<package> --cov-report=term-missing   # Python
jest --coverage                                     # JS
go test ./... -cover                                # Go
```

Coverage tells you **where to look**, not what to test. A module at 40% coverage is a starting point for investigation, not an automatic target for 100%.

### 1.2 Understand the architecture

Before writing tests for a module, answer:
- What does this module do? Thin wrapper or real logic?
- Who calls it? Is it already tested indirectly through callers?
- What are the boundaries between components?

A module at 0% coverage that's a thin wrapper over a well-tested core is low priority. A module at 80% coverage with untested state machine transitions is high priority.

### 1.3 Read existing tests

Understand the patterns: fixtures, mocking strategy, naming conventions, file organization. New tests should look like they belong.

### 1.4 Assess whether you have enough information

Ask yourself: do I understand the codebase well enough to prioritize? If not, read more before reporting. Don't guess.

**CHECKPOINT:** Share your findings with the user before writing anything:
- What's well covered, what's not
- Where real logic lives vs thin wrappers
- Which gaps are most likely to hide bugs
- What you recommend testing first **and why**

Then ask: **"Does this match your understanding? Should I start with X, or do you see different priorities?"**

Verify PREFLIGHT items 1-6 are complete before proceeding.

---

## Phase 2: Prioritize

Not all untested code is equally worth testing. Rank by **likelihood of hiding bugs**, not by coverage percentage.

### High priority — test these first
- **External boundaries** — where untrusted input enters (API endpoints, CLI parsers, tool interfaces, deserialization)
- **State machine transitions** — anywhere code checks `state == X` or calls `transition_to(Y)`
- **Cross-component seams** — where two modules interact and might disagree on invariants
- **Complex branching** — functions with many `if/elif/else` paths, especially error handling
- **Disaster recovery paths** — replay, backup restore, crash recovery — rarely exercised, high blast radius when wrong

### Low priority — test these later or not at all
- Thin wrappers that delegate to well-tested code
- Argparse/CLI boilerplate
- Simple getters and setters
- Code that's about to be rewritten

### When NOT to test

Tell the user when testing effort exceeds value. Examples:
- "This module is 0% coverage but 60% boilerplate — not worth a dedicated effort"
- "This layer is a thin wrapper; the core logic is already tested through its caller"
- "These remaining uncovered lines are all simple error returns — low bug probability"

Saving the user's time by saying "don't bother" is as valuable as writing good tests.

**CHECKPOINT (PREFLIGHT 5-6):** Present the prioritized list. Ask: **"This is the order I'd go in. Want to adjust, or should I start with the first one?"**

---

## Phase 3: Select Test Types

For each target from Phase 2, select which test types to apply. Use the motivation from Phase 0 to guide selection.

### Decision matrix

| Target characteristic | Recommended types |
|---|---|
| Pure function, no side effects | Unit + boundary value |
| State machine / transitions | Unit + property-based (invariants) |
| External input boundary | Unit + boundary + fuzz |
| Multi-component interaction | Integration + property-based (cross-component invariants) |
| File/network I/O | Chaos (corruption, truncation, contention) |
| Concurrent access | Chaos (multi-threaded contention, race conditions) |
| Crash recovery / replay | Chaos (mid-operation crash, corrupted state, replay consistency) |
| API contract with consumers | Contract test |
| Full user workflow | E2E / acceptance |

### Test type reference

**Correctness**
- **Unit** — single function/class, dependencies mocked
- **Integration** — real modules interacting, no mocks at the seam
- **E2E** — full user journey through the running system
- **Acceptance / UAT** — validates business requirements (Given/When/Then)
- **Contract** — API shape agreed between services (consumer-driven)
- **Smoke** — minimal "is it alive?" check

**Input coverage**
- **Boundary value** — inputs at and around edges of valid ranges
- **Equivalence partitioning** — one representative from each class of equivalent inputs
- **Property-based** — machine-generated inputs verify invariants that must always hold
- **Fuzz** — random/malformed inputs to find crashes and security holes

**Resilience**
- **Chaos** — deliberate failures: corrupt files, kill processes, contention, truncated writes
- **Stress** — beyond normal capacity; find breaking point and recovery behavior
- **Load** — sustained high load over time; find memory leaks and degradation
- **Performance** — latency and throughput under normal expected load

**Change safety**
- **Regression** — locks a previously broken scenario so it cannot recur
- **Snapshot** — serializes output; fails on any unreviewed change

**Security**
- **Injection** — SQL, XSS, command injection
- **Auth bypass** — privilege escalation, token manipulation
- **Secrets exposure** — credentials in logs, error messages, responses

---

## Phase 4: Design Test Cases

### Perspective

- **Black-box** — test via public interface only, derive cases from spec
- **White-box** — inspect code structure to find untested branches and paths
- Default to black-box; switch to white-box when hunting specific coverage gaps

### Case format

```
GIVEN  [precondition / system state]
WHEN   [action or input]
THEN   [expected outcome]
```

Minimum per function: one happy path, one error path, relevant boundaries.

### Boundary identification

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

### Domain-specific invariants (for property-based testing)

Generic invariants are a starting point:
- **Roundtrip**: `decode(encode(x)) == x`
- **Idempotency**: `f(f(x)) == f(x)`
- **Commutativity**: `f(a,b) == f(b,a)`
- **Monotonicity**: `a <= b → f(a) <= f(b)`
- **No-crash**: valid-typed input never throws unhandled exception

But the most valuable invariants are **domain-specific** — derived from the system's own rules:

How to find them:
1. Read the system's state machine / transition rules
2. Read the architecture doc or CLAUDE.md for stated principles
3. Ask: **"What must ALWAYS be true, no matter what sequence of operations?"**

Real examples:
- "Terminal nodes never have agent_id set" — found a bug where `fail()` didn't clear `claimed_at`
- "Replay of events produces identical graph to direct operations" — found handlers contradicting state machine
- "Graph is acyclic after any sequence of edge additions" — validates cycle detection
- "Node readiness always matches dependency state" — catches stale readiness computations

Cross-component invariants are where property testing finds real bugs.

### Regression test rule

A regression test must **fail on the unfixed code** and **pass after the fix**. If it passes both ways, it's not testing the bug.

---

## Phase 5: Write and Run

### Code quality
- One logical assertion per test
- Test names describe the scenario: `test_fail_clears_claimed_at_and_timeout`
- No control flow (`if`, `for`) inside tests — parameterize instead
- Mock at the boundary of the unit, not deep inside it

### Framework reference

| Language | Unit | Property-Based | E2E | Fuzz |
|---|---|---|---|---|
| Python | `pytest` | `hypothesis` | `playwright` | `atheris` |
| JS / TS | `jest` / `vitest` | `fast-check` | `playwright` / `cypress` | `jsfuzz` |
| Java | `JUnit 5` | `jqwik` | `Selenium` | `jazzer` |
| Go | `testing` | `rapid` | — | `go-fuzz` |
| Rust | `#[test]` | `proptest` | — | `cargo-fuzz` |

### Validate before reporting

Run all quality checks before telling the user tests are done:
```bash
# Python example
ruff check src tests          # lint
ruff format --check src tests # format
pytest tests/                 # full suite, no regressions
```

All must pass. Do not report success until the full suite is green.

---

## Phase 6: Reflect

**After running tests, stop and assess.** This is the most commonly skipped step and the most valuable.

### Did the tests find anything?

| Result | What to say | What to do next |
|---|---|---|
| Found bugs | Report clearly with details | Go to Phase 7 |
| All passed first try | "No bugs found — value is regression protection" | Consider switching test type |
| Exposed a design flaw | Describe the inconsistency | Discuss with user before acting |

### Was the strategy right?

If hand-written unit tests found nothing, consider escalating:

| Current approach | Escalation |
|---|---|
| Unit tests (manual cases) | → Property-based tests (machine-generated combinations) |
| Property-based (single function) | → Cross-component invariant tests |
| Correctness tests | → Chaos tests (break the infrastructure) |
| All of the above found nothing | The code is probably solid. Move on. |

### Coverage delta

Re-run coverage. Report the delta, but frame it honestly:
- "Coverage went from 39% to 95% — and found 2 bugs along the way"
- "Coverage went from 81% to 88% — no bugs found, but regression protection is in place"
- "Coverage only moved 2% — but the 7 property tests found a real bug that hand-written tests missed"

**Coverage measures exercise, not correctness.**

**CHECKPOINT (IN-FLIGHT 8-9):** Report results to the user. Ask: **"These tests [found N bugs / found no bugs]. Want me to continue with [next target / different approach], or is this enough?"**

---

## Phase 7: Handle Discovered Bugs

When tests discover bugs, **do not assume what the user wants.** Ask:

1. **Fix it and include in the same PR** — tests + fix tell one complete story. Best when the fix is straightforward and you're confident.
2. **Open an issue and leave it** — appropriate when the fix is complex, touches unfamiliar code, or needs design discussion with the team.

The user's relationship with the codebase and the bug's severity both matter. Let them decide.

**If fixing:** bundle tests and fix in one PR. Structure the PR body to tell the discovery story — which test found it, what input triggered it, what the fix was.

**If deferring:** write the test to assert the current (buggy) behavior with a clear docstring explaining what's wrong and what the correct behavior should be. The test documents the bug even if nobody fixes it immediately.

---

## /loop Mode: Sustained Test Discovery

When running as a `/loop`, follow this structure for each round. The goal is systematic exploration with human oversight at each checkpoint.

### Before the loop starts

Complete Phase 0-2 in the first interaction. Establish:
- The motivation
- The prioritized list of targets
- Agreement on scope

This is the roadmap. Each loop iteration works through one target.

### Each round

```
1. Pick the next target from the priority list
2. Select test types (Phase 3)
3. Write and run tests (Phase 4-5)
4. Reflect (Phase 6) — did it find bugs?
5. CHECKPOINT: Report to user
   - "Round N: tested X with Y tests. Found Z bugs / no bugs."
   - "Next up: [next target]. Continue?"
6. If bugs found → Phase 7 (ask user: fix or issue?)
7. Handle branch: commit, push, create PR if user approves
```

### Branch strategy

Each round produces an independent branch from `upstream/main`:

```
upstream/main
  ├── test/unit-tools        ← round 1
  ├── test/replay-tests      ← round 2 (includes fix)
  ├── test/client-coverage   ← round 3
  ├── test/property-tests    ← round 4 (includes fix)
  └── test/chaos-tests       ← round 5 (includes fix)
```

Rules:
- One branch per round, based on `upstream/main`, never stacked
- Rounds that find bugs: tests + fix in the same branch
- Each branch is independently mergeable — no dependencies between rounds
- After merge: sync main, delete branch, continue

### When to stop

Stop when the user says so, or suggest stopping when:
- Two consecutive rounds find no bugs AND
- The remaining targets are low-priority (thin wrappers, boilerplate)

Do not stop autonomously without reporting. Always tell the user what's left and let them decide.

### Round summary format

At each checkpoint:
```
Round N: [target]
  Tests written: X ([test types used])
  Bugs found: Y
  [If bugs: one-line description of each bug]
  Coverage delta: +Z%
  
  Remaining targets: [list]
  Recommendation: [continue / change approach / stop]
```

---

## Anti-patterns

**"Let me increase coverage to 100%"**
Coverage is a reconnaissance tool, not a goal. 100% coverage with no invariant tests finds fewer bugs than 70% coverage with good property tests.

**Writing tests that mirror the implementation**
If renaming an internal variable breaks the test, the test is worthless. Test behavior, not structure.

**Testing only happy paths**
Bugs live in error handling, boundary conditions, and state transitions. Happy paths usually work because developers manually tested them.

**Inflating test value**
When tests pass first try, don't pretend they found something. "Pure regression protection" is a valid and honest outcome.

**Testing everything with equal effort**
A thin wrapper that delegates to well-tested code does not need the same investment as a state machine with 14 transitions.

**Skipping the reflection step**
Writing tests without checking if they found anything is busywork. The point is discovering problems, not producing files.

**Proceeding without user confirmation**
At every checkpoint, the user's input can change direction. Skipping checkpoints leads to wasted work on the wrong thing.

---

## Checklist

Reference this checklist at every phase transition. Items are gates — do not proceed to the next phase until all items in the current section are checked.

### PREFLIGHT (before writing any test)

```
□ Motivation identified and confirmed with user
□ Coverage report generated and reviewed
□ Architecture understood: call chains, thin wrappers vs real logic, indirect coverage
□ Existing test patterns reviewed: fixtures, mocks, naming, file structure
□ Findings reported to user with prioritized target list
□ User has confirmed priorities and starting point
```

### IN-FLIGHT (each round of test writing)

```
□ Test types selected based on target characteristics (refer to decision matrix)
□ Test cases designed: happy path + error path + boundaries
□ Tests written following existing codebase conventions
□ Local validation passed:
    □ Lint check passed
    □ Format check passed
    □ Full test suite green (no regressions)
□ New files have required copyright header
□ Reflection completed:
    □ Did the tests find bugs? (answer honestly)
    □ Is the current strategy working, or should I escalate? (unit → property → chaos)
□ Results reported to user with recommendation for next step
□ User has confirmed: continue / change direction / stop
```

### POST-FLIGHT (after each round, if producing a PR)

```
□ Bug handling confirmed with user: fix in PR / open issue / defer
□ If fixing: tests and fix are in the same commit/branch
□ Commit has Signed-off-by and Co-Authored-By trailers
□ Branch pushed and PR created (if user approves)
□ After merge: main synced with upstream, branch deleted
```

### LOOP SHUTDOWN (when stopping a multi-round session)

```
□ Final summary delivered:
    □ Total rounds run
    □ Total tests written
    □ Total bugs found (with one-line descriptions)
    □ Overall coverage delta
    □ Remaining untested targets (if any)
□ User has confirmed session is complete
```
