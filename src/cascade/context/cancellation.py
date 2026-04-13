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

"""Cascade cancellation mechanism similar to Go context."""

from __future__ import annotations

from asyncio import Event
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from cascade.core.state import NodeState

if TYPE_CHECKING:
    from cascade.core.cascade import Cascade


class CancelledError(Exception):
    """Raised when an operation is cancelled."""

    def __init__(self, reason: str | None = None):
        self.reason = reason
        super().__init__(reason or "Operation cancelled")


@dataclass
class CancellationToken:
    """Token that can be used to cancel operations.

    Provides Go-style context cancellation for async operations.
    """

    _is_cancelled: bool = False
    _reason: str | None = None
    _callbacks: list[Callable[[], None]] = field(default_factory=list)
    _event: Event | None = field(default=None)

    @property
    def is_cancelled(self) -> bool:
        return self._is_cancelled

    @property
    def reason(self) -> str | None:
        return self._reason

    def cancel(self, reason: str | None = None) -> None:
        if self._is_cancelled:
            return
        self._is_cancelled = True
        self._reason = reason
        if self._event:
            self._event.set()
        for callback in self._callbacks:
            try:
                callback()
            except Exception:
                pass

    def throw_if_cancelled(self) -> None:
        if self._is_cancelled:
            raise CancelledError(self._reason)

    def register_callback(self, callback: Callable[[], None]) -> Callable[[], None]:
        if self._is_cancelled:
            callback()
            return lambda: None
        self._callbacks.append(callback)

        def unregister() -> None:
            if callback in self._callbacks:
                self._callbacks.remove(callback)

        return unregister

    def get_event(self) -> Event:
        if self._event is None:
            self._event = Event()
            if self._is_cancelled:
                self._event.set()
        return self._event

    async def wait_for_cancel(self) -> None:
        await self.get_event().wait()

    def __bool__(self) -> bool:
        return not self._is_cancelled


@dataclass
class CancellationPropagator:
    """Handles cascade cancellation through the DAG."""

    cascade: Cascade
    node_tokens: dict[str, CancellationToken] = field(default_factory=dict)

    def create_token(self, node_id: str) -> CancellationToken:
        token = CancellationToken()
        self.node_tokens[node_id] = token

        def on_cancel() -> None:
            self._on_node_cancelled(node_id)

        token.register_callback(on_cancel)
        return token

    def get_token(self, node_id: str) -> CancellationToken | None:
        return self.node_tokens.get(node_id)

    def cancel_node(self, node_id: str, reason: str | None = None, cascade: bool = True) -> None:
        if node_id not in self.cascade.nodes:
            return

        token = self.node_tokens.get(node_id)
        if token:
            token.cancel(reason)

        node = self.cascade.nodes[node_id]
        node.update_state(NodeState.CANCELLED)

        if cascade:
            for dependent in self.cascade.get_dependents(node_id):
                if dependent.state not in (NodeState.CANCELLED, NodeState.COMPLETED):
                    self.cancel_node(
                        dependent.id,
                        f"Cascaded from {node_id}" + (f": {reason}" if reason else ""),
                        cascade=True,
                    )

    def cancel_all(self, reason: str | None = None) -> None:
        for node_id in list(self.cascade.nodes.keys()):
            self.cancel_node(node_id, reason, cascade=False)

    def _on_node_cancelled(self, node_id: str) -> None:
        if node_id in self.cascade.nodes:
            node = self.cascade.nodes[node_id]
            if not node.state.is_terminal():
                node.update_state(NodeState.CANCELLED)

    def get_cancelled_nodes(self) -> list[str]:
        return [node_id for node_id, token in self.node_tokens.items() if token.is_cancelled]

    def reset_node(self, node_id: str) -> None:
        """Reset a node's cancellation state.

        This is an administrative override — it bypasses the normal state
        machine because "un-cancelling" is inherently outside the normal
        lifecycle. Readiness is derived from the graph.
        """
        if node_id in self.node_tokens:
            del self.node_tokens[node_id]
        if node_id in self.cascade.nodes:
            pending = self.cascade.pending_dependency_count(node_id)
            self.cascade.nodes[node_id].state = NodeState.READY if pending == 0 else NodeState.PENDING

    def reset_all(self) -> None:
        self.node_tokens.clear()
        for node_id in self.cascade.nodes:
            pending = self.cascade.pending_dependency_count(node_id)
            self.cascade.nodes[node_id].state = NodeState.READY if pending == 0 else NodeState.PENDING
