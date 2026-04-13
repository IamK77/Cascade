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

"""Cascade - A cascade-based collaboration framework for multi-agent systems."""

__version__ = "0.1.0"

from cascade.context.cancellation import CancellationToken, CancelledError
from cascade.context.propagator import ContextPropagator
from cascade.core.cascade import Cascade
from cascade.core.node import Node
from cascade.core.state import NodeState
from cascade.storage.graph_storage import GraphStorage, LockError
from cascade.types import Context, Contract, ContextKV, ContextLevel, EdgeId
from cascade.view import get_node_view

# Tools (framework-agnostic functions for LLM agents)
from tools.add_node import add_node
from tools.edit_node import edit_node
from tools.finish_task import finish_task
from tools.get_task import get_task
from tools.list_nodes import list_nodes
from tools.refine_node import refine_node
from tools.remove_node import remove_node
from tools.split_node import split_node

__all__ = [
    # Types
    "Context",
    "Contract",
    "ContextKV",
    "ContextLevel",
    "EdgeId",
    # Core
    "Cascade",
    "Node",
    "NodeState",
    # Propagation
    "ContextPropagator",
    "CancellationToken",
    "CancelledError",
    # View
    "get_node_view",
    # Storage
    "GraphStorage",
    "LockError",
    # Tools (structure)
    "add_node",
    "remove_node",
    "split_node",
    "refine_node",
    "edit_node",
    # Tools (execution)
    "get_task",
    "finish_task",
    # Tools (query)
    "list_nodes",
]
