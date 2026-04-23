# Changelog

All notable changes to this project will be documented in this file.
Generated from [conventional commits](https://www.conventionalcommits.org/).

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

