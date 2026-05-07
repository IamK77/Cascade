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

"""Task claim token storage with push/pull cancellation support.

Pull: call check() to read token status.
Push: register a CancelNotifier when claiming — it fires on invalidation.
"""

import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Protocol, runtime_checkable

from cascade.types import TokenStatus


@runtime_checkable
class CancelNotifier(Protocol):
    """Push cancellation interface.

    Implement this to receive cancellation notifications via any
    transport: file, webhook, Redis pub/sub, Unix signal, etc.
    """

    def notify(self, token: TokenStatus) -> None: ...


class FileNotifier:
    """Write cancellation to a file. Simplest built-in adapter."""

    def __init__(self, path: str | Path):
        self._path = Path(path)

    def notify(self, token: TokenStatus) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(token.to_dict(), ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


class CallbackNotifier:
    """Call a Python function on cancellation. For in-process use."""

    def __init__(self, callback: Callable[[TokenStatus], None]):
        self._callback = callback

    def notify(self, token: TokenStatus) -> None:
        self._callback(token)


class FileTokenStore:
    """Manages task claim tokens in .cascade/tokens/.

    Each ACTIVE task has a token file. The token tracks whether the
    claim is still valid and optionally holds a notifier for push
    cancellation.
    """

    def __init__(self, base_dir: Path | str):
        self._dir = Path(base_dir) / "tokens"
        self._notifiers: dict[str, CancelNotifier] = {}

    def _token_path(self, node_id: str) -> Path:
        return self._dir / f"{node_id}.json"

    def create(
        self,
        node_id: str,
        agent_id: str,
        claimed_at: float,
        notifier: CancelNotifier | None = None,
    ) -> TokenStatus:
        """Create a token when an agent claims a task."""
        token = TokenStatus(
            node_id=node_id,
            agent_id=agent_id,
            valid=True,
            claimed_at=claimed_at,
        )
        self._dir.mkdir(parents=True, exist_ok=True)
        self._token_path(node_id).write_text(
            json.dumps(token.to_dict(), ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        if notifier is not None:
            self._notifiers[node_id] = notifier
        return token

    def check(self, node_id: str) -> TokenStatus | None:
        """Public pull interface. Returns token status or None if no token."""
        path = self._token_path(node_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return TokenStatus.from_dict(data)

    def invalidate(self, node_id: str, reason: str) -> TokenStatus | None:
        """Mark a token as invalid and fire push notification if registered."""
        token = self.check(node_id)
        if token is None or not token.valid:
            return token

        token.valid = False
        token.reason = reason
        token.invalidated_at = time.time()

        self._token_path(node_id).write_text(
            json.dumps(token.to_dict(), ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        notifier = self._notifiers.pop(node_id, None)
        if notifier is not None:
            notifier.notify(token)

        return token

    def cleanup(self, node_id: str) -> None:
        """Remove token file after task completes normally."""
        path = self._token_path(node_id)
        if path.exists():
            path.unlink()
        self._notifiers.pop(node_id, None)
