# TODO — Engineering & Integration

Items parked here for later. Architecture-first, engineering follows.

## Integration
- [ ] Update CLI (`cascade/cli.py`) for new API (no `in_degree`, `get_contract()`, `get_node_view` as function)
- [ ] Create CLAUDE.md with agent guidance (available tools, usage patterns, rework flow)
- [ ] Write end-to-end example: build graph → multi-agent claim/complete → rework cycle
- [ ] Generate JSON schemas for all tools (for LLM framework integration)
- [ ] Update README.md to reflect current architecture

## Documentation
- [ ] Document module dependency DAG (types → core → context/storage → view → operations → tools)
- [ ] Document state machine transitions with rework and release paths
- [ ] Document context propagation rules and rework-as-forward-derivation pattern
