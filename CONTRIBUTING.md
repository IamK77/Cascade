# Contributing to Cascade

Thank you for your interest in contributing to Cascade! This document provides guidelines and instructions for contributing.

## Code of Conduct

By participating in this project, you agree to maintain a respectful and inclusive environment for all contributors.

## How to Contribute

### Reporting Bugs

If you find a bug, please open an issue with the following information:

- **Description**: A clear description of the bug
- **Steps to Reproduce**: Minimal code example or commands
- **Expected Behavior**: What you expected to happen
- **Actual Behavior**: What actually happened
- **Environment**: Python version, OS, package versions

### Suggesting Features

Feature suggestions are welcome! Please open an issue with:

- **Description**: Clear description of the feature
- **Use Case**: Why this feature would be useful
- **Proposal**: Optional implementation ideas

### Pull Requests

1. **Fork** the repository
2. **Create a branch** from `main`:
   ```bash
   git checkout -b feat/your-feature-name
   # or
   git checkout -b fix/your-bug-fix
   ```
3. **Install pre-commit hooks** (one-time setup, automates lint/format/type checks):
   ```bash
   pip install pre-commit
   pre-commit install
   ```
4. **Make your changes** following the code style guidelines
5. **Add tests** for new functionality
6. **Run tests** to ensure everything passes:
   ```bash
   uv run pytest
   ```
   (lint, format, and mypy run automatically on `git commit` via pre-commit)
7. **Commit** with a clear message (see Commit Guidelines)
8. **Push** and open a Pull Request

## Development Setup

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager

### Setup

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/cascade.git
cd cascade

# Install dependencies
uv sync

# Activate virtual environment
source .venv/bin/activate  # Linux/macOS
# or
.venv\Scripts\activate     # Windows
```

## Code Style Guidelines

### Python Style

- Follow [PEP 8](https://peps.python.org/pep-0008/) conventions
- Maximum line length: 100 characters
- Use type hints for all public functions and classes
- Use docstrings for public APIs

### Formatting

We use [Ruff](https://docs.astral.sh/ruff/) for linting and formatting:

```bash
# Check code
uv run ruff check src tests

# Format code
uv run ruff format src tests
```

### Type Checking

We use [mypy](https://mypy-lang.org/) with strict mode:

```bash
uv run mypy src
```

## Commit Guidelines

Follow the [Conventional Commits](https://www.conventionalcommits.org/) specification:

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types

| Type | Description |
|------|-------------|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `test` | Adding or updating tests |
| `refactor` | Code change without fixing bug or adding feature |
| `perf` | Performance improvement |
| `chore` | Maintenance tasks |
| `ci` | CI/CD changes |

### Examples

```
feat(context): add timeout support for cancellation tokens
```

```
fix(storage): resolve race condition in file locking

Fix concurrent access issue when multiple agents try to acquire
locks simultaneously.
```

## Testing

### Running Tests

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=src --cov-report=html

# Run specific test file
uv run pytest tests/unit/test_node.py
```

### Writing Tests

- Place unit tests in `tests/unit/`
- Place integration tests in `tests/integration/`
- Use descriptive test names: `test_<function>_<scenario>_<expected>`
- Use fixtures for common setup (see `tests/conftest.py`)

## Project Structure

Module dependency chain (verified acyclic): `types → core → context → view → operations → tools`

```
cascade/
├── src/
│   ├── cascade/           # Core library
│   │   ├── types.py       # Value types (Contract, Context, ContextEntry, TokenStatus)
│   │   ├── core/          # Cascade graph, Node, NodeState
│   │   ├── context/       # BFS ancestor propagation + cancellation
│   │   ├── view.py        # Upstream view builder (get_node_view)
│   │   ├── events.py      # Append-only event store (14 event types)
│   │   ├── operations/    # Compound operations (Split, Remove, Rework)
│   │   ├── storage/       # JSON persistence + file locking + token store
│   │   ├── viz.py         # DAG visualization (mermaid, ASCII)
│   │   └── cli.py         # Command-line interface (13 commands)
│   └── tools/             # LLM agent tool functions (12 tools)
├── tests/                 # Unit, integration, and scenario tests
├── docs/
│   ├── guide.md           # Comprehensive usage guide
│   └── i18n/              # Translated READMEs (zh-CN, ja, es)
└── pyproject.toml         # Project configuration
```

## License

By contributing, you agree that your contributions will be licensed under the Apache-2.0 License.

## Questions?

Feel free to open an issue for any questions about contributing.
