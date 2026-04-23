# TODO — Engineering & Integration

Items parked here for later. Architecture-first, engineering follows.

## Done (2026-04-22/23)
- [x] Update CLI for new API (no `in_degree`, `get_contract()`, 12 tools, `reason` params, `check-task`)
- [x] Create CLAUDE.md with agent guidance
- [x] Write end-to-end example: Rust port via Cascade (9 nodes, 8 agents, 79 Rust tests)
- [x] Document module dependency DAG
- [x] Document state machine transitions with rework and release paths
- [x] Document context propagation rules (upstream view with path/distance/contract)
- [x] Context propagation redesign — attributed entries, no merge, no overwrite
- [x] Event coverage for all mutation tools + reason parameter
- [x] ACTIVE node protection (remove/split refused)
- [x] Token-based cancellation (TokenStore + CancelNotifier protocol)
- [x] CancellationToken bridged to CancelNotifier (one semantic, two implementations)

## Remaining
- [ ] Generate JSON schemas for all tools (for LLM framework integration)
- [ ] Update README.md to reflect current architecture
- [ ] Dynamic operations validation — design experiment that naturally triggers rework/split in real multi-agent workflow
