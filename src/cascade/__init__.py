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

"""Cascade - A DAG-based multi-agent task scheduling framework."""

__version__ = "0.4.8"

from cascade.client import CascadeClient
from cascade.context.cancellation import CancellationToken
from cascade.context.propagator import ContextPropagator
from cascade.core.cascade import Cascade
from cascade.core.node import Node
from cascade.core.state import NodeState
from cascade.errors import (
    CancelledError,
    CascadeError,
    ContractError,
    CycleError,
    InvalidTransitionError,
    LockError,
    NodeExistsError,
    NodeNotFoundError,
)
from cascade.storage.content import ContentStore, GitContentStore, LocalContentStore
from cascade.storage.file_storage import FileStorage
from cascade.storage.protocol import StorageProtocol
from cascade.storage.token_store import CancelNotifier, FileNotifier, TokenStore
from cascade.types import (
    Context,
    ContextEntry,
    ContextKV,
    Contract,
    DeliveredContext,
    DependencyInfo,
    EdgeId,
    ErrorCode,
    NodeInfo,
    PromiseEntry,
    Result,
    TaskView,
    TokenStatus,
    UpstreamEntry,
)
from cascade.view import get_node_view

__all__ = [
    # Client
    "CascadeClient",
    # Types
    "Context",
    "Contract",
    "ContextKV",
    "ContextEntry",
    "DeliveredContext",
    "DependencyInfo",
    "EdgeId",
    "ErrorCode",
    "NodeInfo",
    "PromiseEntry",
    "Result",
    "TaskView",
    "TokenStatus",
    "UpstreamEntry",
    # Core
    "Cascade",
    "Node",
    "NodeState",
    # Errors
    "CascadeError",
    "NodeNotFoundError",
    "NodeExistsError",
    "CycleError",
    "InvalidTransitionError",
    "ContractError",
    "LockError",
    # Cancellation
    "CancelNotifier",
    "CancellationToken",
    "CancelledError",
    "FileNotifier",
    "TokenStore",
    # Propagation
    "ContextPropagator",
    # View
    "get_node_view",
    # Storage
    "ContentStore",
    "FileStorage",
    "GitContentStore",
    "LocalContentStore",
    "StorageProtocol",
    "LockError",
]
