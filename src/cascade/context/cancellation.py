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

from asyncio import Event
from collections.abc import Callable
from dataclasses import dataclass, field

from cascade.core.cascade import Cascade
from cascade.core.state import NodeState


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
        """Check if cancellation was requested."""
        return self._is_cancelled

    @property
    def reason(self) -> str | None:
        """Get cancellation reason."""
        return self._reason

    def cancel(self, reason: str | None = None) -> None:
        """Trigger cancellation.

        Args:
            reason: Optional reason for cancellation
        """
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
        """Raise exception if cancelled.

        Raises:
            CancelledError: If cancellation was requested
        """
        if self._is_cancelled:
            raise CancelledError(self._reason)

    def register_callback(self, callback: Callable[[], None]) -> Callable[[], None]:
        """Register a callback to be called on cancellation.

        Args:
            callback: Function to call when cancelled

        Returns:
            Unregister function
        """
        if self._is_cancelled:
            callback()
            return lambda: None

        self._callbacks.append(callback)

        def unregister() -> None:
            if callback in self._callbacks:
                self._callbacks.remove(callback)

        return unregister

    def get_event(self) -> Event:
        """Get an async event that is set on cancellation.

        Returns:
            asyncio.Event that is set when cancelled
        """
        if self._event is None:
            self._event = Event()
            if self._is_cancelled:
                self._event.set()
        return self._event

    async def wait_for_cancel(self) -> None:
        """Wait until cancellation is requested.

        This is useful for long-running operations to check for cancellation.
        """
        await self.get_event().wait()

    def __bool__(self) -> bool:
        """Allow truthy check for cancellation status."""
        return not self._is_cancelled


@dataclass
class CancellationPropagator:
    """Handles cascade cancellation through the DAG.

    When a node is cancelled, all its dependents are also cancelled.
    This mimics Go's context cancellation propagation.
    """

    cascade: Cascade
    """The DAG to propagate cancellation through."""

    node_tokens: dict[str, CancellationToken] = field(default_factory=dict)
    """Mapping of node IDs to their cancellation tokens."""

    def create_token(self, node_id: str) -> CancellationToken:
        """Create a cancellation token for a node.

        Args:
            node_id: Node ID to create token for

        Returns:
            New cancellation token
        """
        token = CancellationToken()
        self.node_tokens[node_id] = token

        def on_cancel() -> None:
            self._on_node_cancelled(node_id)

        token.register_callback(on_cancel)
        return token

    def get_token(self, node_id: str) -> CancellationToken | None:
        """Get existing cancellation token for a node.

        Args:
            node_id: Node ID to get token for

        Returns:
            Existing token or None
        """
        return self.node_tokens.get(node_id)

    def cancel_node(self, node_id: str, reason: str | None = None, cascade: bool = True) -> None:
        """Cancel a node and optionally cascade to dependents.

        Args:
            node_id: Node ID to cancel
            reason: Optional reason for cancellation
            cascade: Whether to cascade to dependents
        """
        if node_id not in self.cascade.nodes:
            return

        token = self.node_tokens.get(node_id)
        if token:
            token.cancel(reason)

        self.cascade.nodes[node_id].state = NodeState.CANCELLED

        if cascade:
            for dependent in self.cascade.get_dependents(node_id):
                if dependent.state not in (
                    NodeState.CANCELLED,
                    NodeState.COMPLETED,
                ):
                    self.cancel_node(
                        dependent.id,
                        f"Cascaded from {node_id}" + (f": {reason}" if reason else ""),
                        cascade=True,
                    )

    def cancel_all(self, reason: str | None = None) -> None:
        """Cancel all nodes in the DAG.

        Args:
            reason: Optional reason for cancellation
        """
        for node_id in list(self.cascade.nodes.keys()):
            self.cancel_node(node_id, reason, cascade=False)

    def _on_node_cancelled(self, node_id: str) -> None:
        """Internal callback when a node's token is cancelled.

        Args:
            node_id: Node that was cancelled
        """
        if node_id in self.cascade.nodes:
            self.cascade.nodes[node_id].state = NodeState.CANCELLED

    def get_cancelled_nodes(self) -> list[str]:
        """Get list of cancelled node IDs.

        Returns:
            List of cancelled node IDs
        """
        return [node_id for node_id, token in self.node_tokens.items() if token.is_cancelled]

    def reset_node(self, node_id: str) -> None:
        """Reset a node's cancellation state.

        This allows a cancelled node to be re-executed.
        The node's state is reset to READY if it has no dependencies.

        Args:
            node_id: Node ID to reset
        """
        if node_id in self.node_tokens:
            del self.node_tokens[node_id]

        if node_id in self.cascade.nodes:
            node = self.cascade.nodes[node_id]
            if node.in_degree == 0:
                node.state = NodeState.READY
            else:
                node.state = NodeState.PENDING

    def reset_all(self) -> None:
        """Reset all cancellation states."""
        self.node_tokens.clear()

        for node in self.cascade.nodes.values():
            if node.in_degree == 0:
                node.state = NodeState.READY
            else:
                node.state = NodeState.PENDING
