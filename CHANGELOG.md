# Changelog

All notable changes to this project will be documented in this file.
Generated from [conventional commits](https://www.conventionalcommits.org/).

## [0.4.11] - 2026-05-07

### Documentation

- Update CHANGELOG.md for v0.4.10

### Miscellaneous

- Bump to 0.4.11

### Refactored

- Protocol-ize storage sub-components for distributed backends
## [0.4.10] - 2026-05-07

### Added

- Downstream verification tip — claim prompts delivery review
- Deliverables gate and compact briefing format
- Extract tips module — structured guidance at operation boundaries
- Hybrid logical clock replaces pure Lamport counter
- Rework supersession — skip context from reworked nodes
- Mandatory fencing token on finish operations
- Verify-chain CLI command for event log integrity audit
- Opencode-compatible cascade skill with self-claim worker pool
- Watch emits ready_tasks after each transition batch
- Actionable tips across all operations
- Trace_id — correlate events within a single operation
- Event hash chain — tamper-evident event log
- Reject reserved critical keys (produced_at, git_ref)

### Documentation

- Skill — add worktree isolation guidance and protocol compliance recovery
- Align skill with agentskills.io spec + enrich content
- Update CHANGELOG.md for v0.4.9

### Fixed

- Correct repo URL from autoseek/cascade to autoseek-ai/Cascade

### Miscellaneous

- Bump to 0.4.10

### Refactored

- Expose Cascade internal APIs, seal encapsulation boundary
- Replace hand-rolled utilities with stdlib
- Separate provenance from critical — framework metadata gets its own type
- Remove redundant runtime type checks
## [0.4.9] - 2026-05-06

### Added

- Context freshness — auto-embed provenance on complete

### Documentation

- Update for v0.4.8 — Result API, context freshness, StorageProtocol
- Update CHANGELOG.md for v0.4.8

### Fixed

- Render_inspect shows Freshness, drop _ prefix convention

### Miscellaneous

- Bump to 0.4.9
## [0.4.8] - 2026-05-06

### Added

- Temporal query layer — show, diff, snapshot-at
- Extract ContentStore protocol with local + git implementations
- Event replay — rebuild graph state from event log
- Idempotent operations via op_id
- Distributed prep — event identity, storage protocol, fencing tokens

### Documentation

- Update CHANGELOG.md for v0.4.6
- Skill — promote Adapt table, level markers, collapse rules
- Update CHANGELOG.md for v0.4.4

### Fixed

- Split no longer triggers duplicate-promise warning
- Use structured artifacts_ref field instead of string prefix detection
- Remove save_node() — incomplete incremental persistence
- Remove write-only agent_tasks from graph.json
- Let cycle detection errors propagate instead of silently degrading
- Let cancellation callback errors propagate
- Let cascade remove propagate errors instead of swallowing them

### Miscellaneous

- Bump to 0.4.8
- Bump to 0.4.7
- Bump to 0.4.6

### Refactored

- Unify client API — claim/nodes return Result, projections via types
- Events reference content store instead of inlining artifacts
- Clean up tools layer + organize test structure
- Introduce exception hierarchy, replace bare ValueError
- Extract _mutate transaction + move result types to types.py
- Lamport owned by storage, not EventStore
- Tighten types — TypedDict for view layer
- Persist Lamport clock to dedicated file instead of log scan

### Testing

- Fix duplicate-promise warnings in test data
## [0.4.4] - 2026-04-28

### Documentation

- Skill audit — fix CLI mismatches, prune redundancy
- Update CHANGELOG.md for v0.4.3

### Fixed

- Claim with existing active task now fails with ALREADY_HAS_ACTIVE

### Miscellaneous

- Bump to 0.4.4
## [0.4.3] - 2026-04-28

### Added

- Cascade watch + error codes on Result

### Documentation

- Skill — hardened sub-agent template + failure code reference
- Update CHANGELOG.md for v0.4.2

### Fixed

- Lint and type errors from v0.4.2 changes

### Miscellaneous

- Bump to 0.4.3
- Add pre-commit hooks for ruff and mypy

### Style

- Ruff format on v0.4.2 changes
## [0.4.2] - 2026-04-28

### Added

- Cascade add-nodes for atomic batch DAG construction

### Documentation

- Skill — add-nodes pattern + edge-triggered notifications
- Update CHANGELOG.md for v0.4.1

### Miscellaneous

- Bump to 0.4.2
## [0.4.1] - 2026-04-28

### Added

- Harden orchestrator workflow — agent verification, retry, inspect
- Markdown briefing for get-task CLI output

### Documentation

- Acknowledge Mode A/B design distribution + spec ownership
- Tighten skill — cut redundancy, fix CLI mismatches
- Skill improvements from experiment analysis
- Update CHANGELOG.md for v0.4.0

### Fixed

- Add --version flag to CLI and sync __version__ to 0.4.0

### Miscellaneous

- Bump to 0.4.1
## [0.4.0] - 2026-04-27

### Added

- Add CascadeClient as single API layer
- Add algo-lib example task for Cascade parallel experiment
- Cross-platform file locking via filelock
- Include Claude Code skill in repository

### Documentation

- Add task-tracker example with dependency chains
- Update all docs to CascadeClient API, bump v0.4.0
- Emphasize minimal Agent prompts in skill guide
- Add parallel execution guide to skill
- Skill focuses on CLI only, add pipx/uv tool install
- Note macOS/Linux requirement in README
- Add check-task command doc, fix skill imports
- Add pip install cascade-auto to all installation sections
- Update CHANGELOG.md for v0.3.0

### Fixed

- Skill auto-runs cascade --help on load, sync user/project level
- Add threading.Lock for intra-process thread safety
- Use cascade imports instead of tools in all docs

### Refactored

- Migrate all tests to CascadeClient API
- CLI + tools delegate to CascadeClient
## [0.3.0] - 2026-04-23

### Added

- Bridge CancellationToken to CancelNotifier protocol
- Add token-based cancellation with pull/push interfaces
- Protect ACTIVE nodes from remove and split
- Warn on duplicate promise for edges to same node
- Complete event coverage for all DAG mutation tools
- Redesign context propagation with attributed upstream view
- Update CLI with all 11 commands
- Event sourcing — append-only audit trail
- Critical path scheduling and DAG visualization
- Add timeout mechanism and allow independent task groups
- Add rework mechanism for upstream feedback
- Enforce mandatory contract for all edges
- Initialize Cascade multi-agent task scheduling framework

### CI

- Automate CHANGELOG via git-cliff on tag push

### Documentation

- Update CHANGELOG.md for v0.3.0
- Update CHANGELOG.md for v0.3.0
- Add architecture, security policy, sync translations
- Rewrite README for current architecture, update CONTRIBUTING
- Update guide.md for upstream view, cancellation, and CLI changes
- Update TODO.md — mark completed items from v0.3 session
- Rewrite usage.md as guide.md with full coverage
- Move i18n to docs/i18n/ and update changelog for v0.2.0
- Update all documentation and add i18n (en/zh/ja/es)
- CLAUDE.md and README.md via 4-agent Cascade workflow
- Add contributing guide and changelog

### Fixed

- Add contents:read permission for publish workflow
- Trigger publish on tag push instead of release event
- Format all code + fix release workflow for private repos
- Resolve CI lint and type errors
- Context flow — agent output was silently dropped

### Miscellaneous

- Prepare v0.3.0 release as cascade-auto
- Remove TODO.md — track remaining items via GitHub Issues
- Add token tests, update CLAUDE.md, bridge CancellationPropagator
- Open-source hygiene for v0.2.0

### Refactored

- Enforce acyclic module boundaries
- Rebuild type system to eliminate implicit assumptions

### Testing

- Verify dynamic graph editing during execution

### Demo

- Dynamic graph editing simulation with 4 agents
- Re-run multi-agent workflow with working context flow

