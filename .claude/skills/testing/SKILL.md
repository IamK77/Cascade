---
name: testing
description: >
  Systematically design, generate, and review tests for software projects.
  Trigger when the user mentions testing, wants to write tests, asks how to test
  a function/module/API, mentions unit tests, integration tests, edge cases,
  property-based testing, coverage, or says things like "help me test this",
  "what should I test", "write tests for this code", "I just fixed a bug".
argument-hint: "[target-module-or-scope]"
allowed-tools: Read Bash Edit Write
---

# Software Testing

Testing is a collaboration. You bring systematic coverage; the user brings domain knowledge and judgment calls. Neither works well alone.

Every phase has a **CHECKPOINT** — pause and interact with the user before proceeding. Do not skip checkpoints. At each checkpoint, **list the completed checklist items by number** (e.g., "PREFLIGHT 1-4 ✓") so the user can verify progress and so you cannot silently skip steps.

If `$ARGUMENTS` is provided, treat it as the target module or scope to test (e.g., `/testing replay.py` or `/testing cancellation subsystem`). If the argument doesn't look like a test target (e.g., a language preference), acknowledge it and still ask for the test target separately.

## References

- For test type selection, see [references/types.md](references/types.md)
- For case design, boundaries, invariants, and frameworks, see [references/design.md](references/design.md)

Load these when you reach the relevant phase, not upfront.

---

## Phase 0: Understand the Motivation

| Motivation | Strategy |
|---|---|
| "I fixed a bug" | Regression test — reproduce the exact failure |
| "I'm refactoring" | High unit coverage as a safety net |
| "I want to find unknown bugs" | Property-based, chaos, cross-component invariants |
| "I'm going to prod soon" | Smoke + E2E critical paths |
| "The system crashes under load" | Stress, chaos, concurrent contention |
| "I want general confidence" | Start with reconnaissance, then decide |

**CHECKPOINT (PREFLIGHT 1):** If the motivation is unclear, ask: **"What's prompting this — a bug, a refactor, a release, or just general confidence?"** Output "PREFLIGHT 1 ✓" when confirmed. Do not proceed until you know.

---

## Phase 1: Reconnaissance

**Do not write tests yet.** First understand what exists.

1. Run coverage and review the report
2. Understand the architecture: what does each module do? Thin wrapper or real logic? Already tested indirectly through callers?
3. Read existing test patterns: fixtures, mocks, naming, file organization
4. Assess whether you have enough information to prioritize — if not, read more

A module at 0% coverage that's a thin wrapper over a well-tested core is low priority.
A module at 80% coverage with untested state machine transitions is high priority.

**CHECKPOINT (PREFLIGHT 2-5):** Share findings with the user:
- What's well covered, what's not
- Where real logic lives vs thin wrappers
- Which gaps are most likely to hide bugs
- What you recommend testing first **and why**

Ask: **"Does this match your understanding? Should I start with X, or do you see different priorities?"**

Output "PREFLIGHT 2-5 ✓" when reconnaissance is complete and findings are shared.

---

## Phase 2: Prioritize

Rank by **likelihood of hiding bugs**, not by coverage percentage.

**High priority — test first:**
- External boundaries (where untrusted input enters)
- State machine transitions
- Cross-component seams (where modules might disagree on invariants)
- Complex branching (especially error handling)
- Disaster recovery paths (rarely exercised, high blast radius)

**Low priority — test later or skip:**
- Thin wrappers delegating to well-tested code
- CLI/argparse boilerplate
- Simple getters and setters
- Code about to be rewritten

**When NOT to test:** tell the user when effort exceeds value. Saving the user's time by saying "don't bother" is as valuable as writing good tests.

**CHECKPOINT (PREFLIGHT 6):** Present the prioritized list. Ask: **"This is the order I'd go in. Want to adjust, or should I start with the first one?"**

Output "PREFLIGHT 1-6 ✓ — all gates passed" before proceeding to Phase 3.

---

## Phase 3: Select Test Types

Load [references/types.md](references/types.md) for the decision matrix and type glossary.

Match target characteristics to test types. Use the motivation from Phase 0 to guide selection.

---

## Phase 4: Design and Write

Load [references/design.md](references/design.md) for case format, boundary tables, invariants, and framework reference.

**Perspective:**
- Black-box (default) — test via public interface
- White-box — inspect code to find untested branches; use when hunting coverage gaps

**Validate before reporting:**
- Lint check passed
- Format check passed
- Full test suite green (no regressions)
- New files have required copyright header

---

## Phase 5: Reflect

**After running tests, stop and assess.**

### Did the tests find anything?

| Result | What to say | Next step |
|---|---|---|
| Found bugs | Report with details | Go to Phase 6 |
| All passed first try | "No bugs found — value is regression protection" | Consider escalating strategy |
| Exposed a design flaw | Describe the inconsistency | Discuss before acting |

### Strategy escalation

If the current approach found nothing, consider switching:

| Current | Escalation |
|---|---|
| Unit tests (manual cases) | → Property-based (machine-generated combinations) |
| Property-based (single function) | → Cross-component invariant tests |
| Correctness tests | → Chaos tests (break the infrastructure) |
| All above found nothing | The code is probably solid. Move on. |

### Coverage delta

Re-run coverage. Report honestly:
- Coverage is a reconnaissance tool, not a goal
- "Coverage went up 20% but found no bugs" is an honest outcome
- "Coverage moved 2% but found a real bug" is a great outcome

**CHECKPOINT (IN-FLIGHT 8-9):** Report results. Output "IN-FLIGHT 1-9 ✓" with the round summary. Ask: **"These tests [found N bugs / found no bugs]. Want me to continue with [next target / different approach], or is this enough?"**

---

## Phase 6: Handle Discovered Bugs

**Do not assume what the user wants.** Ask:

1. **Fix it and include in the same PR** — tests + fix tell one complete story
2. **Open an issue and leave it** — for complex fixes or when design discussion is needed

**If fixing:** bundle tests and fix in one PR. Structure the PR body to tell the discovery story.

**If deferring:** write the test asserting current (buggy) behavior with a docstring explaining what's wrong and what correct behavior should be.

---

## /loop Mode

For sustained test discovery across multiple rounds.

### Before the loop starts

**Critical:** once the loop begins, opportunities for user interaction are limited. All alignment must happen upfront.

Complete Phase 0-2 fully before the first loop iteration:
1. Confirm motivation
2. Run reconnaissance, share findings
3. Agree on the prioritized target list
4. Agree on bug handling policy: "fix in PR" or "open issue" (set a default so the loop doesn't block on every bug)
5. Agree on branch/PR workflow: auto-push each round, or batch?
6. Output "PREFLIGHT 1-6 ✓ — entering loop" before starting

### Each round

1. Pick next target from priority list
2. Select types, design, write, run (Phase 3-5)
3. Output "IN-FLIGHT 1-9 ✓" with round summary
4. Handle bugs per the pre-agreed policy
5. Handle branch: commit, push, create PR
6. If a decision cannot be made without user input, **stop the loop and ask** — do not guess

### Branch strategy

One branch per round, based on `upstream/main`, never stacked:
- Rounds that find bugs: tests + fix in the same branch
- Each branch is independently mergeable
- After merge: sync main, delete branch, continue

### When to stop

Stop when the user says so, or suggest stopping when:
- Two consecutive rounds find no bugs AND remaining targets are low-priority

Do not stop without reporting. Always tell the user what's left and let them decide.

### Round summary format

```
Round N: [target]
  Tests written: X ([test types used])
  Bugs found: Y
  [If bugs: one-line description of each]
  Coverage delta: +Z%
  Remaining targets: [list]
  Recommendation: [continue / change approach / stop]
```

---

## Checklist

Reference at every phase transition. Items are gates — do not proceed until checked.

### PREFLIGHT (before writing any test)

```
□ 1. Motivation identified and confirmed with user
□ 2. Coverage report generated and reviewed
□ 3. Architecture understood: call chains, wrappers vs logic, indirect coverage
□ 4. Existing test patterns reviewed: fixtures, mocks, naming, structure
□ 5. Findings reported to user with prioritized target list
□ 6. User has confirmed priorities and starting point
```

### IN-FLIGHT (each round of test writing)

```
□ 1. Test types selected (consult decision matrix in references/types.md)
□ 2. Test cases designed: happy path + error path + boundaries
□ 3. Tests written following existing codebase conventions
□ 4. Lint check passed
□ 5. Format check passed
□ 6. Full test suite green (no regressions)
□ 7. New files have required copyright header
□ 8. Reflection completed: found bugs? Strategy working or escalate?
□ 9. Results reported to user, next step confirmed
```

### POST-FLIGHT (after each round, if producing a PR)

```
□ 1. Bug handling confirmed with user: fix in PR / open issue / defer
□ 2. If fixing: tests and fix in same branch
□ 3. Commit has Signed-off-by and Co-Authored-By trailers
□ 4. Branch pushed and PR created (if user approves)
□ 5. After merge: main synced with upstream, branch deleted
```

### LOOP SHUTDOWN (when stopping a multi-round session)

```
□ 1. Final summary: rounds run, tests written, bugs found, coverage delta
□ 2. Remaining untested targets listed
□ 3. User has confirmed session is complete
```

---

## Anti-patterns

- **Chasing 100% coverage** — coverage is reconnaissance, not a goal
- **Mirroring implementation** — test behavior, not structure
- **Testing only happy paths** — bugs live in error handling and transitions
- **Inflating test value** — "no bugs found, regression protection" is honest
- **Equal effort everywhere** — thin wrappers don't need the same investment as state machines
- **Skipping reflection** — writing tests without checking if they found anything is busywork
- **Skipping checkpoints** — the user's input at every checkpoint can change direction
