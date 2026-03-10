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

from cascade.protocols.context_protocol import (
    ContextKV,
    ContextLevel,
    ContextProtocol,
)


@dataclass
class Context:
    """Concrete implementation of context propagation.

    Context carries information through the DAG at different levels:
    - Critical: Key-value data that propagates indefinitely
    - Summary: Brief description for grandchildren
    - Artifacts: Relative path to markdown file (.dag/artifacts/{node_id}.md)

    Note: artifacts stores a file path pointer, not the actual content.
    The path is always relative to the project root (e.g., .dag/artifacts/node_a.md).
    """

    critical: ContextKV = field(default_factory=dict)
    summary: str = ""
    artifacts: str = ""

    def propagate_to(self, level: ContextLevel, distance: int) -> bool:
        """Determine if context should propagate to given distance.

        Args:
            level: Context level to check
            distance: Distance from source node (0 = self)

        Returns:
            True if context should propagate

        Note:
            - ARTIFACTS stores a file path pointer, which always propagates
            - The actual artifact content is stored separately in .dag/artifacts/
        """
        if level == ContextLevel.CRITICAL:
            # Critical propagates indefinitely
            return True
        elif level == ContextLevel.SUMMARY:
            # Summary propagates to grandchildren (distance <= 2)
            return distance <= 2
        elif level == ContextLevel.ARTIFACTS:
            # Artifacts path pointer always propagates (lightweight reference)
            return True
        return False

    def merge(self, other: ContextProtocol) -> "Context":
        """Merge another context into this one.

        Args:
            other: Context to merge

        Returns:
            New merged context
        """
        merged_critical = {**self.critical}
        if hasattr(other, "critical"):
            merged_critical.update(other.critical)

        merged_summary = self.summary
        if hasattr(other, "summary") and other.summary:
            if merged_summary:
                merged_summary += "\n" + other.summary
            else:
                merged_summary = other.summary

        merged_artifacts = self.artifacts
        if hasattr(other, "artifacts") and other.artifacts:
            if merged_artifacts:
                merged_artifacts += "\n" + other.artifacts
            else:
                merged_artifacts = other.artifacts

        return Context(
            critical=merged_critical,
            summary=merged_summary,
            artifacts=merged_artifacts,
        )

    def describe(self) -> str:
        """Generate human-readable description.

        Returns:
            Formatted description string
        """
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
        """Set a critical key-value pair.

        Args:
            key: Key to set
            value: Value to set

        Returns:
            Self for method chaining
        """
        self.critical[key] = value
        return self

    def get_critical(self, key: str, default: Any = None) -> Any:
        """Get a critical value.

        Args:
            key: Key to get
            default: Default value if key not found

        Returns:
            Value or default
        """
        return self.critical.get(key, default)

    def __repr__(self) -> str:
        critical_keys = list(self.critical.keys())[:3]
        critical_str = str(critical_keys) if critical_keys else "{}"
        summary_preview = self.summary[:30] + "..." if len(self.summary) > 30 else self.summary
        artifacts_preview = (
            self.artifacts[:30] + "..." if len(self.artifacts) > 30 else self.artifacts
        )
        return f"Context(critical={critical_str}, summary={summary_preview!r}, artifacts={artifacts_preview!r})"

    def has_artifacts(self) -> bool:
        """Check if this context has an artifacts file reference.

        Returns:
            True if artifacts path is set
        """
        return bool(self.artifacts)

    def get_artifacts_path(self) -> str:
        """Get the artifacts file path.

        Returns:
            Relative path to artifacts file (.dag/artifacts/{node_id}.md)
        """
        return self.artifacts

    def set_artifacts_path(self, path: str) -> "Context":
        """Set the artifacts file path.

        Args:
            path: Relative path to artifacts file (e.g., .dag/artifacts/{node_id}.md)

        Returns:
            Self for method chaining
        """
        self.artifacts = path
        return self
