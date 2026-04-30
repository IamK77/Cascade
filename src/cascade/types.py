# Copyright 2026 Hangzhou Autoseek Information Technology Co., Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Shared type definitions for the Cascade framework.

This module is the single source of truth for all value types.
No module in cascade/ may depend on anything other than this module
and the standard library.

Dependency rule: types.py → (nothing in cascade/)
"""

from dataclasses import asdict, dataclass, field
from typing import Any, TypeAlias, TypedDict

# ---------------------------------------------------------------------------
# Edge identifier
# ---------------------------------------------------------------------------
EdgeId: TypeAlias = tuple[str, str]
"""(from_id, to_id) — from_id is the dependency, to_id is the dependent."""


# ---------------------------------------------------------------------------
# Contract — expectation/promise pair on every edge.
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Contract:
    """Expectation/promise pair stored on a directed edge.

    Every edge in the Cascade carries exactly one Contract.
    - expectation: what the dependent expects from the dependency.
    - promise: what the dependency promises to provide.

    Both fields are required and non-empty — enforced by Cascade.add_edge().
    """

    expectation: str
    promise: str


# ---------------------------------------------------------------------------
# Context — value type carried by nodes.
# ---------------------------------------------------------------------------
ContextKV: TypeAlias = dict[str, Any]
"""Key-value pairs for critical context propagation."""


# ---------------------------------------------------------------------------
# Token — task claim status for cancellation support.
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class TokenStatus:
    """Status of a task claim token.

    Created when an agent claims a task. Invalidated when the task
    is released, reworked, timed out, or cancelled. Provides both
    pull (check()) and push (CancelNotifier) cancellation interfaces.
    """

    node_id: str
    agent_id: str
    valid: bool
    claimed_at: float
    reason: str = ""
    invalidated_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TokenStatus":
        return cls(**{k: v for k, v in d.items() if k in cls.__slots__})


# ---------------------------------------------------------------------------
# Context entry — upstream contribution with provenance.
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class ContextEntry:
    """An upstream node's contribution to the current node's context.

    Each entry represents one ancestor and what it delivered.
    Direct parents (distance 1) include the contract (expectation/promise).
    Further ancestors include the traversal path for provenance.
    """

    node_id: str
    state: str
    distance: int
    path: list[str] = field(default_factory=list)
    expectation: str = ""
    promise: str = ""
    summary: str = ""
    critical: ContextKV = field(default_factory=dict)
    artifacts: str = ""


@dataclass
class Context:
    """Context carried by a node — its own output, not inherited data.

    Three fields:
    - critical: KV data (propagation distance owned by ContextPropagator).
    - summary: Brief description of what the node accomplished.
    - artifacts: Content string (persisted to file by storage layer).

    Context is never merged across nodes. Multi-source collection
    produces list[ContextEntry] via ContextPropagator, keeping each
    source's contribution separate and attributed.
    """

    critical: ContextKV = field(default_factory=dict)
    summary: str = ""
    artifacts: str = ""

    def describe(self) -> str:
        """Generate human-readable description."""
        parts = ["# Context\n"]
        if self.critical:
            parts.append("## Critical (KV)")
            for key, value in self.critical.items():
                parts.append(f"- {key}: {value}")
            parts.append("")
        if self.summary:
            parts.append("## Summary")
            parts.append(self.summary)
            parts.append("")
        return "\n".join(parts).strip()

    def set_critical(self, key: str, value: Any) -> "Context":
        """Set a critical key-value pair. Returns self for chaining."""
        self.critical[key] = value
        return self

    def get_critical(self, key: str, default: Any = None) -> Any:
        """Get a critical value."""
        return self.critical.get(key, default)

    def __repr__(self) -> str:
        critical_keys = list(self.critical.keys())[:3]
        critical_str = str(critical_keys) if critical_keys else "{}"
        summary_preview = self.summary[:30] + "..." if len(self.summary) > 30 else self.summary
        artifacts_preview = (
            self.artifacts[:30] + "..." if len(self.artifacts) > 30 else self.artifacts
        )
        return f"Context(critical={critical_str}, summary={summary_preview!r}, artifacts={artifacts_preview!r})"


# ---------------------------------------------------------------------------
# View layer TypedDicts — typed shapes for agent-facing data.
# ---------------------------------------------------------------------------


class DeliveredContext(TypedDict, total=False):
    """What an upstream node delivered."""

    summary: str
    critical: ContextKV
    artifacts: str


class UpstreamEntry(TypedDict, total=False):
    """One upstream node's contribution to a task's briefing."""

    node_id: str
    state: str
    distance: int
    path: list[str]
    expectation: str
    promise: str
    delivered: DeliveredContext


class PromiseEntry(TypedDict):
    """A promise this node made to a downstream dependent."""

    to_node: str
    promise: str


class DependencyInfo(TypedDict):
    """Dependency metadata for a node."""

    node_id: str
    expectation: str | None
    promise: str | None
