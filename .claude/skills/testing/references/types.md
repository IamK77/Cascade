# Test Type Reference

## Decision Matrix

Use this to select test types based on what you're testing.

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

## Type Glossary

### Correctness
- **Unit** — single function/class, dependencies mocked
- **Integration** — real modules interacting, no mocks at the seam
- **E2E** — full user journey through the running system
- **Acceptance / UAT** — validates business requirements (Given/When/Then)
- **Contract** — API shape agreed between services (consumer-driven)
- **Smoke** — minimal "is it alive?" check

### Input coverage
- **Boundary value** — inputs at and around edges of valid ranges
- **Equivalence partitioning** — one representative from each class of equivalent inputs
- **Property-based** — machine-generated inputs verify invariants that must always hold
- **Fuzz** — random/malformed inputs to find crashes and security holes

### Resilience
- **Chaos** — deliberate failures: corrupt files, kill processes, contention, truncated writes
- **Stress** — beyond normal capacity; find breaking point and recovery behavior
- **Load** — sustained high load over time; find memory leaks and degradation
- **Performance** — latency and throughput under normal expected load

### Change safety
- **Regression** — locks a previously broken scenario so it cannot recur
- **Snapshot** — serializes output; fails on any unreviewed change

### Security
- **Injection** — SQL, XSS, command injection
- **Auth bypass** — privilege escalation, token manipulation
- **Secrets exposure** — credentials in logs, error messages, responses
