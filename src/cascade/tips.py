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

"""Structured tips — contextual guidance at operation boundaries.

Each phase (claim, complete, fail, refine, rework) has one public
function that returns a list of tips. Tips carry a level:

- ADVISORY: helpful hint, included in the result message.
- REQUIRED: gate — the operation is rejected unless satisfied.

Dependency rule: tips.py → types.py
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class TipLevel(Enum):
    ADVISORY = "advisory"
    REQUIRED = "required"


@dataclass(frozen=True, slots=True)
class Tip:
    message: str
    level: TipLevel = TipLevel.ADVISORY


# ---------------------------------------------------------------------------
# Phase evaluators
# ---------------------------------------------------------------------------


def on_claim(
    *,
    task_id: str,
    upstream: list[dict[str, Any]],
    promises: list[dict[str, Any]],
    was_previously_released: bool,
) -> list[Tip]:
    tips: list[Tip] = []

    verify_lines: list[str] = []
    for u in upstream:
        nid = u.get("node_id", "")
        delivered = u.get("delivered", {})
        has_context = bool(
            delivered.get("summary") or delivered.get("critical") or delivered.get("artifacts")
        )

        if u.get("state") == "COMPLETED" and not has_context:
            tips.append(
                Tip(
                    f"upstream '{nid}' delivered no context"
                    " — you may need to inspect its output directly."
                )
            )

        prov = delivered.get("provenance", {})
        deliverables = prov.get("deliverables", {})
        if deliverables:
            delivered_text = deliverables.get(task_id, "")
            if delivered_text and u.get("promise"):
                verify_lines.append(
                    f'{nid} promised: "{u["promise"]}"'
                    f' → delivered: "{delivered_text}"'
                    f' — verify this meets your expectation: "{u.get("expectation", "")}"'
                )

    if verify_lines:
        tips.append(Tip("Verify upstream delivery before proceeding:\n" + "\n".join(verify_lines)))

    if was_previously_released:
        tips.append(
            Tip(
                "this task was previously released by another agent — check history for the reason."
            )
        )

    if promises:
        lines: list[str] = []
        for p in promises:
            lines.append(
                f'{p["to_node"]} expects: "{p["expectation"]}" — You promise: "{p["promise"]}"'
            )
        tips.append(Tip("\n".join(lines)))

    return tips


def on_complete(
    *,
    summary: str,
    critical: dict[str, Any],
    artifacts: str,
    promises: list[dict[str, Any]],
    deliverables: dict[str, str] | None,
    has_dependents: bool,
) -> list[Tip]:
    tips: list[Tip] = []

    if not summary and not critical and not artifacts and has_dependents:
        tips.append(
            Tip("no context delivered — downstream agents will receive nothing from this node.")
        )

    if promises:
        if deliverables is None:
            lines = [f'  → {p["to_node"]}: "{p["promise"]}"' for p in promises]
            tips.append(
                Tip(
                    f"Cannot complete: {len(promises)} promise(s) require delivery confirmation.\n"
                    + "\n".join(lines)
                    + "\nResubmit with a deliverable for each promise.",
                    level=TipLevel.REQUIRED,
                )
            )
        else:
            promised_targets = {p["to_node"] for p in promises}
            delivered_targets = set(deliverables.keys())
            missing = promised_targets - delivered_targets
            if missing:
                lines = []
                for p in promises:
                    if p["to_node"] in missing:
                        lines.append(f'  → {p["to_node"]}: "{p["promise"]}"')
                tips.append(
                    Tip(
                        f"Missing deliverables for {len(missing)} promise(s):\n"
                        + "\n".join(lines)
                        + "\nResubmit with a deliverable for each promise.",
                        level=TipLevel.REQUIRED,
                    )
                )

    return tips


def on_fail(*, cascade: bool, affected_count: int) -> list[Tip]:
    tips: list[Tip] = []

    if cascade and affected_count > 1:
        tips.append(Tip("use list-nodes to review affected scope."))

    return tips


def on_refine(*, node_id: str, dep_id: str, old_state: str, new_state: str) -> list[Tip]:
    tips: list[Tip] = []

    if old_state == "READY" and new_state == "PENDING":
        tips.append(
            Tip(f"node '{node_id}' was READY, now PENDING — blocked until '{dep_id}' completes.")
        )

    return tips


def on_rework(*, active_node_id: str, corrective_node_id: str) -> list[Tip]:
    return [
        Tip(
            f"your task '{active_node_id}' is now PENDING until"
            f" '{corrective_node_id}' completes — you cannot reclaim until then."
        )
    ]


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def has_required(tips: list[Tip]) -> bool:
    return any(t.level == TipLevel.REQUIRED for t in tips)


def required_messages(tips: list[Tip]) -> list[str]:
    return [t.message for t in tips if t.level == TipLevel.REQUIRED]


def append_tips(message: str, tips: list[Tip]) -> str:
    if not tips:
        return message
    tip_text = " ".join(f"Tip: {t.message}" for t in tips)
    return f"{message}. {tip_text}"
