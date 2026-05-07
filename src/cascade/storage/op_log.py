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

"""Idempotent operation log.

Stores executed operation IDs and their results so that retried
requests with the same op_id return the cached result instead of
re-executing. Provides at-least-once → exactly-once semantics.
"""

import json
from pathlib import Path
from typing import Any


class FileOpLog:
    """Persists op_id → result mappings to .cascade/ops.json."""

    def __init__(self, base_dir: Path | str):
        self._path = Path(base_dir) / "ops.json"
        self._cache: dict[str, dict[str, Any]] | None = None

    def _load(self) -> dict[str, dict[str, Any]]:
        if self._cache is not None:
            return self._cache
        if not self._path.exists():
            self._cache = {}
            return self._cache
        try:
            self._cache = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            self._cache = {}
        return self._cache

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._load(), ensure_ascii=False), encoding="utf-8")

    def get(self, op_id: str) -> dict[str, Any] | None:
        """Return cached result for op_id, or None if not seen before."""
        return self._load().get(op_id)

    def record(self, op_id: str, result: dict[str, Any]) -> None:
        """Record an executed operation and its result."""
        self._load()[op_id] = result
        self._save()
