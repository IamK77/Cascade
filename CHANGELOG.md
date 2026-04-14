# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-04-14

### Added

#### Type System

- `cascade/types.py` — single source of truth for all value types
- `Contract(frozen=True)` — typed expectation/promise pair replacing `dict[str, str | None]`
- `EdgeId = tuple[str, str]` — replaces `"from->to"` string encoding
- `Context` moved to `types.py` to break circular dependency between core and context

#### Features

- **Rework mechanism** — forward-only upstream feedback via corrective nodes. Inspired by Go's `context.WithValue`: never mutate the parent, derive a new child.
- **Event sourcing** — append-only JSONL log (`events.jsonl`) recording all graph mutations. Query via `history` tool.
- **Critical path scheduling** — `get_ready_nodes` sorts by downstream depth. Longest chain first.
- **DAG visualization** — `to_mermaid()` and `to_ascii()` in `cascade/viz.py`. Critical path highlighted.
- **Timeout / heartbeat** — `claimed_at` and `timeout` on Node. `check_timeouts` tool releases stalled tasks.
- **Independent task groups** — connected graph constraint removed. Multiple roots allowed.

#### New Tools

- `rework` — request upstream correction (creates corrective node)
- `check_timeouts` — scan and release stalled ACTIVE tasks
- `history` — query the event log (by node, by type, summary)

### Changed

#### Type System Overhaul

- Node: removed `in_degree` field — readiness now computed by `Cascade.pending_dependency_count()`
- Node: removed `increment_in_degree()` / `decrement_in_degree()` methods
- Cascade: `edge_metadata: dict[str, dict]` → `_contracts: dict[EdgeId, Contract]` (encapsulated)
- Cascade: `adjacency_list` / `reverse_adjacency` → `_adjacency` / `_reverse` (encapsulated)
- Cascade: PENDING/READY transitions centralized in `_update_readiness()`
- Cascade: `notify_completion()` replaces manual `decrement_in_degree` calls
- Cascade: `_restore_edge()` for storage deserialization (recomputes readiness on load)
- State machine: transitions encoded as `_VALID_TRANSITIONS` frozenset data, not if-else chains
- State machine: added ACTIVE → READY (release), PENDING/READY → FAILED (cascade failure)
- `OperationResult` made generic with `TypeVar` — typed payloads per operation
- `finish_task`: `result` param renamed to `summary` (backward-compatible alias kept)
- `finish_task`: added `critical` param for structured KV output
- `finish_task`: auto-creates `Context` if node has none — output never silently dropped

#### Architecture

- `get_node_view()` extracted from `Cascade` into `cascade/view.py` (presentation vs graph primitive)
- Module dependency graph verified as DAG: `types → core → context → view → operations → tools`
- `protocols/` package removed — `NodeProtocol` and `ContextProtocol` replaced by concrete types
- All `hasattr` checks removed (zero remaining)
- All direct `.state =` assignments in tools replaced with `update_state()` (4 exceptions documented)

#### Operations Layer

- `AddOperation` removed — tools call Cascade primitives directly
- `RefineOperation` removed — tools call Cascade primitives directly
- `SplitOperation`, `RemoveOperation` kept — genuine compound operations
- `ReworkOperation` added

### Fixed

- Context propagation: `finish_task` silently dropped agent output when `node.context` was None
- `NodeState.is_finished()` had redundant `self != READY` check — removed
- Storage artifacts: removed `len > 100` heuristic for path vs content detection — always save to file

### Documentation

- README.md rewritten with current architecture
- i18n: added Chinese (`docs/i18n/README.zh-CN.md`), Japanese (`README.ja.md`), Spanish (`README.es.md`)
- CLAUDE.md updated to reflect current module structure and tool inventory
- Cascade skill docs synced: 11 commands documented, stale `in_degree` / connected graph references removed

## [0.1.0] - 2026-03-10

### Added

#### Core Features

- **DAG Task Scheduling**: Tasks with dependencies and automatic state transitions
  - Node states: `PENDING` → `READY` → `ACTIVE` → `COMPLETED`/`FAILED`/`CANCELLED`
  - Automatic state management based on dependency completion

- **Context Propagation**: Three-level context system
  - `critical`: Key-value pairs (latest wins on conflict)
  - `summary`: Text summaries concatenated from upstream
  - `artifacts`: Detailed output storage
  - Context flows downstream to dependent tasks

- **Contract System**: Expectation/promise contracts stored on edges
  - Different promises to different downstream tasks
  - Flexible task relationship definitions

- **Multi-Agent Coordination**: Agent tracking and task assignment
  - One task per agent constraint
  - Agent ID tracking for task ownership

- **Cascade Cancellation**: Go-style context cancellation propagation
  - `CancellationToken` for cancellation signaling
  - Automatic propagation to dependent tasks on failure

- **Persistence Layer**: File-based storage with locking
  - JSON-based graph storage
  - Concurrent access protection with file locking

#### CLI Interface

- `cascade add-node`, `get-task`, `finish-task`, `list-nodes`
- `cascade split-node`, `refine-node`, `remove-node`, `edit-node`

#### Tool Functions (Framework-Agnostic)

- `add_node`, `get_task`, `finish_task`, `list_nodes`
- `split_node`, `refine_node`, `remove_node`, `edit_node`

#### Testing & Setup

- Unit and integration tests
- Python 3.11+, uv, Ruff, mypy strict, pytest-asyncio

[Unreleased]: https://github.com/autoseek/cascade/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/autoseek/cascade/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/autoseek/cascade/releases/tag/v0.1.0
