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

"""Protocol interface definitions for context."""

from enum import Enum
from typing import Any, Protocol, TypeAlias


class ContextLevel(Enum):
    """Context propagation level.

    - CRITICAL: KV format, propagates indefinitely (critical for all descendants)
    - SUMMARY: Node summary, propagates to grandchildren only (distance <= 2)
    - ARTIFACTS: Full MD overview, stored in files only (no direct propagation)
    """

    CRITICAL = 1
    SUMMARY = 2
    ARTIFACTS = 3


ContextKV: TypeAlias = dict[str, Any]


class ContextProtocol(Protocol):
    """Protocol interface for context propagation.

    Context carries information through the Cascade:
    - Critical: Key-value data that must propagate to all descendants
    - Summary: Brief description that propagates to grandchildren
    - Artifacts: Full markdown documentation stored separately
    """

    @property
    def critical(self) -> ContextKV:
        """Critical key-value information."""
        ...

    @critical.setter
    def critical(self, value: ContextKV) -> None:
        """Set critical key-value information."""
        ...

    @property
    def summary(self) -> str:
        """Brief node summary."""
        ...

    @summary.setter
    def summary(self, value: str) -> None:
        """Set brief node summary."""
        ...

    @property
    def artifacts(self) -> str:
        """Full markdown documentation."""
        ...

    @artifacts.setter
    def artifacts(self, value: str) -> None:
        """Set full markdown documentation."""
        ...

    def propagate_to(self, level: ContextLevel, distance: int) -> bool:
        """Determine if context should propagate to given distance.

        Args:
            level: Context level to check
            distance: Distance from source node (0 = self, 1 = child/parent, etc.)

        Returns:
            True if context should propagate to this distance
        """
        ...

    def merge(self, other: "ContextProtocol") -> "ContextProtocol":
        """Merge another context into this one.

        Args:
            other: Context to merge

        Returns:
            New merged context
        """
        ...

    def describe(self) -> str:
        """Generate human-readable description.

        Returns:
            Formatted description string
        """
        ...
