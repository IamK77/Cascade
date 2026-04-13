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

This module is the single source of truth for all cross-cutting types.
Every type here encodes a design invariant — no implicit assumptions.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, TypeAlias


# ---------------------------------------------------------------------------
# Edge identifier — replaces the "from_id->to_id" string encoding.
# A tuple is hashable, indexable, and self-documenting.
# ---------------------------------------------------------------------------
EdgeId: TypeAlias = tuple[str, str]
"""(from_id, to_id) — from_id is the dependency, to_id is the dependent."""


# ---------------------------------------------------------------------------
# Contract — the expectation/promise pair stored on every edge.
# Frozen because a contract, once established, should be renegotiated
# explicitly rather than mutated in place.
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Contract:
    """Expectation/promise pair stored on a directed edge.

    Every edge in the Cascade carries exactly one Contract.
    - expectation: what the dependent (to_id) expects from the dependency (from_id)
    - promise: what the dependency (from_id) promises to provide to the dependent (to_id)

    Both fields are required and non-empty — this is enforced at construction
    by Cascade.add_edge(), not here, to keep the dataclass a pure value type.
    """

    expectation: str
    promise: str


# ---------------------------------------------------------------------------
# Context types
# ---------------------------------------------------------------------------
ContextKV: TypeAlias = dict[str, Any]
"""Key-value pairs for critical context propagation."""


class ContextLevel(Enum):
    """Context propagation level.

    Controls how far each category of context information travels
    through the DAG:

    - CRITICAL: KV pairs, propagates indefinitely to all descendants.
    - SUMMARY: Text, propagates to grandchildren only (distance <= 2).
    - ARTIFACTS: File path pointer, always propagates (lightweight reference).
    """

    CRITICAL = 1
    SUMMARY = 2
    ARTIFACTS = 3
