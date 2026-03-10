# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Placeholder for upcoming features

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
  - `LockError` exception for lock acquisition failures

#### CLI Interface

- `cascade add-node` - Create a new task
- `cascade get-task` - Claim a task to work on
- `cascade finish-task` - Complete, fail, or release a task
- `cascade list-nodes` - View all tasks and their states
- `cascade split-node` - Break down a complex task
- `cascade refine-node` - Add a dependency to a task
- `cascade remove-node` - Delete a task
- `cascade edit-node` - Update task properties

#### Python API

- `Cascade` - Main graph class
- `Node` - Task node representation
- `NodeState` - State enumeration
- `Context` - Context container
- `ContextPropagator` - Context propagation logic
- `CancellationToken` / `CancelledError` - Cancellation support
- `GraphStorage` - Persistence backend

#### Tool Functions (Framework-Agnostic)

- `add_node()` - Add task to DAG
- `get_task()` - Claim available task
- `finish_task()` - Complete or fail task
- `list_nodes()` - Query tasks
- `split_node()` - Decompose task
- `refine_node()` - Add dependency
- `remove_node()` - Remove task
- `edit_node()` - Modify task properties

#### Testing

- Unit tests for core components
- Integration tests for workflows
- Test fixtures in `conftest.py`
- pytest-asyncio support

#### Documentation

- README with quick start guide
- Detailed usage documentation (`docs/usage.md`)
- API examples and integration guides

### Project Setup

- Python 3.11+ requirement
- uv package manager support
- Ruff linter/formatter configuration
- mypy strict mode type checking
- pytest configuration with asyncio support
- Coverage reporting configuration

[Unreleased]: https://github.com/autoseek/cascade/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/autoseek/cascade/releases/tag/v0.1.0
