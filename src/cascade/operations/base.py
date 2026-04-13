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

"""Base class for node operations."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from cascade.core.cascade import Cascade

T = TypeVar("T")


@dataclass
class OperationResult(Generic[T]):
    """Result of a node operation.

    Generic over the data payload so each operation can declare what
    it returns on success. On failure, data is None.
    """

    success: bool
    affected_nodes: list[str]
    message: str
    data: T | None

    def __init__(
        self,
        success: bool,
        affected_nodes: list[str],
        message: str = "",
        data: T | None = None,
    ):
        self.success = success
        self.affected_nodes = affected_nodes
        self.message = message
        self.data = data

    def __repr__(self) -> str:
        status = "Success" if self.success else "Failed"
        return f"OperationResult({status}, nodes={len(self.affected_nodes)})"


class NodeOperation(ABC):
    """Base class for all node operations."""

    def __init__(self, cascade: Cascade):
        self._cascade = cascade

    @abstractmethod
    def execute(self, *args: Any, **kwargs: Any) -> OperationResult[Any]:
        ...

    def validate(self) -> tuple[bool, str | None]:
        is_acyclic = self._cascade.find_cycle() is None
        error = None
        if not is_acyclic:
            cycle_info = self._cascade.find_cycle()
            error = f"Graph contains cycle: {cycle_info}"
        return is_acyclic, error

    def _validate_node_exists(self, node_id: str) -> tuple[bool, str | None]:
        if node_id not in self._cascade.nodes:
            return False, f"Node {node_id} not found"
        return True, None

    def _validate_nodes_exist(self, node_ids: list[str]) -> tuple[bool, str | None]:
        for node_id in node_ids:
            valid, error = self._validate_node_exists(node_id)
            if not valid:
                return False, error
        return True, None
