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

"""Context implementation for information propagation."""

from dataclasses import dataclass, field
from typing import Any

from cascade.types import ContextKV, ContextLevel


@dataclass
class Context:
    """Context carried by a node for downstream propagation.

    Three levels of information:
    - critical: Key-value data that propagates indefinitely.
    - summary: Brief description, propagates to grandchildren (distance <= 2).
    - artifacts: Content string (persisted to file by storage layer).
    """

    critical: ContextKV = field(default_factory=dict)
    summary: str = ""
    artifacts: str = ""

    def propagate_to(self, level: ContextLevel, distance: int) -> bool:
        """Determine if context should propagate to given distance."""
        if level == ContextLevel.CRITICAL:
            return True
        elif level == ContextLevel.SUMMARY:
            return distance <= 2
        elif level == ContextLevel.ARTIFACTS:
            return True
        return False

    def merge(self, other: "Context") -> "Context":
        """Merge another context into this one, returning a new Context."""
        merged_critical = {**self.critical, **other.critical}

        merged_summary = self.summary
        if other.summary:
            merged_summary = f"{merged_summary}\n{other.summary}" if merged_summary else other.summary

        merged_artifacts = self.artifacts
        if other.artifacts:
            merged_artifacts = f"{merged_artifacts}\n{other.artifacts}" if merged_artifacts else other.artifacts

        return Context(
            critical=merged_critical,
            summary=merged_summary,
            artifacts=merged_artifacts,
        )

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
        artifacts_preview = self.artifacts[:30] + "..." if len(self.artifacts) > 30 else self.artifacts
        return f"Context(critical={critical_str}, summary={summary_preview!r}, artifacts={artifacts_preview!r})"
