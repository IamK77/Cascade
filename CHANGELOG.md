# Changelog

All notable changes to this project will be documented in this file.
Generated from [conventional commits](https://www.conventionalcommits.org/).

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

