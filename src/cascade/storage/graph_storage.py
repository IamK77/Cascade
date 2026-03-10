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

"""Storage for Cascade persistence."""

import fcntl
import json
from contextlib import contextmanager
from enum import Enum
from pathlib import Path
from typing import Any, Generator, IO

from cascade.context.context import Context
from cascade.core.cascade import Cascade
from cascade.core.node import Node
from cascade.core.state import NodeState


class StorageScope(Enum):
    """Storage scope for graph persistence."""

    PROJECT = "project"  # 项目级: <workspace>/.cascade/
    USER = "user"  # 用户级: ~/.cascade/


class LockError(Exception):
    """Raised when lock cannot be acquired."""

    pass


class GraphStorage:
    """Handles persistence of Cascade structures with file locking.

    Storage structure:
        base_dir/
            graph.json        # Graph structure (nodes, edges, states)
            .lock             # Lock file for concurrent access
            artifacts/
                <node_id>.md   # Artifacts content per node
    """

    def __init__(
        self,
        base_dir: Path | str | None = None,
        scope: StorageScope = StorageScope.PROJECT,
    ):
        """Initialize storage.

        Args:
            base_dir: Base directory for storage (overrides default)
            scope: Storage scope (PROJECT or USER), ignored if base_dir is provided
        """
        if base_dir is not None:
            self.base_dir = Path(base_dir)
        elif scope == StorageScope.USER:
            self.base_dir = Path.home() / ".cascade"
        else:
            self.base_dir = Path.cwd() / ".cascade"

        self.artifacts_dir = self.base_dir / "artifacts"
        self._lock_file: IO[str] | None = None
        self._lock_path = self.base_dir / ".lock"

    @classmethod
    def project(cls, base_dir: Path | str | None = None) -> "GraphStorage":
        """Create project-level storage."""
        return cls(base_dir=base_dir, scope=StorageScope.PROJECT)

    @classmethod
    def user(cls) -> "GraphStorage":
        """Create user-level storage."""
        return cls(scope=StorageScope.USER)

    def exists(self) -> bool:
        """Check if saved data exists."""
        return (self.base_dir / "graph.json").exists()

    @contextmanager
    def lock(self, timeout: float = 10.0, blocking: bool = True) -> Generator[None, None, None]:
        """Acquire file lock for atomic operations.

        Usage:
            with storage.lock():
                cascade = storage.load()
                # ... modifications ...
                storage.save(cascade)

        Args:
            timeout: Maximum seconds to wait for lock (default: 10.0)
            blocking: If False, raise LockError immediately if lock unavailable

        Yields:
            None

        Raises:
            LockError: If lock cannot be acquired (when blocking=False or timeout)
        """
        import time

        self.base_dir.mkdir(parents=True, exist_ok=True)

        # Open/create lock file
        self._lock_file = open(self._lock_path, "w")

        start_time = time.time()
        while True:
            try:
                flag = fcntl.LOCK_EX
                if not blocking:
                    flag |= fcntl.LOCK_NB

                fcntl.flock(self._lock_file.fileno(), flag)
                break
            except (IOError, OSError):
                if not blocking:
                    self._lock_file.close()
                    self._lock_file = None
                    raise LockError("Could not acquire lock: another process holds it")
                if time.time() - start_time >= timeout:
                    self._lock_file.close()
                    self._lock_file = None
                    raise LockError(f"Could not acquire lock within {timeout} seconds")
                time.sleep(0.1)

        try:
            yield
        finally:
            if self._lock_file:
                fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_UN)
                self._lock_file.close()
                self._lock_file = None

    def atomic_load(self, timeout: float = 10.0) -> Cascade | None:
        """Load Cascade with automatic locking.

        This acquires a lock, loads the data, and returns.
        Caller must call atomic_save() to release the lock.

        **Prefer using lock() context manager instead:**
            with storage.lock():
                cascade = storage.load()
                storage.save(cascade)

        Args:
            timeout: Maximum seconds to wait for lock

        Returns:
            Cascade instance or None if no saved data
        """
        self._lock_file = open(self._lock_path, "w")
        import time

        start_time = time.time()
        while True:
            try:
                fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_EX)
                break
            except (IOError, OSError):
                if time.time() - start_time >= timeout:
                    self._lock_file.close()
                    self._lock_file = None
                    raise LockError(f"Could not acquire lock within {timeout} seconds")
                time.sleep(0.1)

        return self._load_unlocked()

    def atomic_save(self, cascade: Cascade) -> None:
        """Save Cascade and release lock acquired by atomic_load().

        Args:
            cascade: Cascade instance to save
        """
        try:
            self._save_unlocked(cascade)
        finally:
            if self._lock_file:
                fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_UN)
                self._lock_file.close()
                self._lock_file = None

    def save(self, cascade: Cascade) -> None:
        """Save the Cascade to storage.

        Note: For concurrent access, use lock() context manager:
            with storage.lock():
                storage.save(cascade)

        Args:
            cascade: Cascade instance to save
        """
        self._save_unlocked(cascade)

    def _save_unlocked(self, cascade: Cascade) -> None:
        """Internal save without locking."""
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

        # Build graph data
        graph_data: dict[str, Any] = {
            "nodes": {},
            "edges": [],
            "agent_tasks": {},  # agent_id -> task_id mapping for quick lookup
        }

        for node_id, node in cascade.nodes.items():
            node_data: dict[str, Any] = {
                "id": node.id,
                "state": node.state.name,
                "in_degree": node.in_degree,
            }

            # Save agent_id if assigned
            if node.agent_id:
                node_data["agent_id"] = node.agent_id
                # Build agent_tasks index for ACTIVE tasks
                if node.state == NodeState.ACTIVE:
                    graph_data["agent_tasks"][node.agent_id] = node_id

            # Handle context
            if node.context:
                ctx_data: dict[str, Any] = {}

                if node.context.critical:
                    ctx_data["critical"] = node.context.critical

                if node.context.summary:
                    ctx_data["summary"] = node.context.summary

                # Handle artifacts - save to separate file and store path
                if node.context.artifacts:
                    artifacts_content = node.context.artifacts
                    # Check if it's content (not just a path)
                    if (
                        not artifacts_content.startswith(".cascade/")
                        and len(artifacts_content) > 100
                    ):
                        # It's content, save to file
                        artifacts_path = self._save_artifacts(node_id, artifacts_content)
                        ctx_data["artifacts"] = artifacts_path
                    else:
                        ctx_data["artifacts"] = node.context.artifacts

                if ctx_data:
                    node_data["context"] = ctx_data

            graph_data["nodes"][node_id] = node_data

        # Save edges with metadata
        for from_id, dependents in cascade.adjacency_list.items():
            for to_id in dependents:
                edge_key = f"{from_id}->{to_id}"
                metadata = cascade.edge_metadata.get(edge_key, {})
                edge_data: dict[str, str] = {
                    "from": from_id,
                    "to": to_id,
                }
                expectation = metadata.get("expectation")
                if expectation:
                    edge_data["expectation"] = expectation
                promise = metadata.get("promise")
                if promise:
                    edge_data["promise"] = promise
                graph_data["edges"].append(edge_data)

        # Write graph.json
        graph_path = self.base_dir / "graph.json"
        graph_path.write_text(
            json.dumps(graph_data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def save_node(self, cascade: Cascade, node_id: str) -> None:
        """Save a single node incrementally.

        Note: For concurrent access, use lock() context manager.

        Args:
            cascade: Cascade instance
            node_id: ID of node to save
        """
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

        # Load existing data
        graph_path = self.base_dir / "graph.json"
        if graph_path.exists():
            graph_data = json.loads(graph_path.read_text(encoding="utf-8"))
        else:
            graph_data = {"nodes": {}, "edges": []}

        node = cascade.nodes.get(node_id)
        if not node:
            return

        # Build node data
        node_data: dict[str, Any] = {
            "id": node.id,
            "state": node.state.name,
            "in_degree": node.in_degree,
        }

        # Save agent_id if assigned
        if node.agent_id:
            node_data["agent_id"] = node.agent_id

        if node.context:
            ctx_data: dict[str, Any] = {}

            if node.context.critical:
                ctx_data["critical"] = node.context.critical

            if node.context.summary:
                ctx_data["summary"] = node.context.summary

            if node.context.artifacts:
                artifacts_content = node.context.artifacts
                if not artifacts_content.startswith(".cascade/") and len(artifacts_content) > 100:
                    artifacts_path = self._save_artifacts(node_id, artifacts_content)
                    ctx_data["artifacts"] = artifacts_path
                else:
                    ctx_data["artifacts"] = node.context.artifacts

            if ctx_data:
                node_data["context"] = ctx_data

        graph_data["nodes"][node_id] = node_data
        graph_path.write_text(
            json.dumps(graph_data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def load(self) -> Cascade | None:
        """Load Cascade from storage.

        Note: For concurrent access, use lock() context manager:
            with storage.lock():
                cascade = storage.load()

        Returns:
            Cascade instance or None if no saved data
        """
        return self._load_unlocked()

    def _load_unlocked(self) -> Cascade | None:
        """Internal load without locking."""
        graph_path = self.base_dir / "graph.json"
        if not graph_path.exists():
            return None

        try:
            graph_data = json.loads(graph_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

        cascade = Cascade()

        # Load nodes
        for node_id, node_data in graph_data.get("nodes", {}).items():
            state = NodeState[node_data.get("state", "PENDING")]
            in_degree = node_data.get("in_degree", 0)
            agent_id = node_data.get("agent_id")

            # Build context if present
            context = None
            if "context" in node_data:
                ctx_data = node_data["context"]
                artifacts = ctx_data.get("artifacts", "")

                # Try to load artifacts from file
                if artifacts.startswith(".cascade/artifacts/"):
                    filename = artifacts.replace(".cascade/artifacts/", "")
                    artifacts_path = self.base_dir / "artifacts" / filename
                    if artifacts_path.exists():
                        artifacts = artifacts_path.read_text(encoding="utf-8")
                    else:
                        artifacts = ""

                context = Context(
                    critical=ctx_data.get("critical", {}),
                    summary=ctx_data.get("summary", ""),
                    artifacts=artifacts,
                )

            node = Node(
                id=node_id,
                state=state,
                in_degree=in_degree,
                context=context,
                agent_id=agent_id,
            )

            cascade.add_node(node)

        # Load edges: {from, to, expectation?, promise?}
        for edge in graph_data.get("edges", []):
            from_id = edge.get("from")
            to_id = edge.get("to")
            expectation = edge.get("expectation")
            promise = edge.get("promise")

            if from_id in cascade.nodes and to_id in cascade.nodes:
                # Add edge without incrementing in_degree (already set from saved data)
                cascade.adjacency_list[from_id].add(to_id)
                cascade.reverse_adjacency[to_id].add(from_id)

                # Store edge metadata (source of truth for contracts)
                edge_key = f"{from_id}->{to_id}"
                cascade.edge_metadata[edge_key] = {
                    "expectation": expectation,
                    "promise": promise,
                }

        return cascade

    def delete(self) -> None:
        """Delete all saved data."""
        import shutil

        if self.base_dir.exists():
            shutil.rmtree(self.base_dir)

    def _save_artifacts(self, node_id: str, content: str) -> str:
        """Save artifacts content to file.

        Args:
            node_id: Node ID
            content: Artifacts content

        Returns:
            Relative path to artifacts file
        """
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

        artifacts_path = self.artifacts_dir / f"{node_id}.md"
        artifacts_path.write_text(content, encoding="utf-8")

        return f".cascade/artifacts/{node_id}.md"
