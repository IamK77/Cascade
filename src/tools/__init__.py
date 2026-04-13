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

"""LLM Tools for Cascade Scheduler.

Framework-agnostic tool functions for LLM agents. Each tool:
- Takes (GraphStorage, dict) and returns dict (the LLM serialization boundary)
- Handles file locking and persistence internally
- Either calls Cascade primitives directly (simple ops) or
  delegates to Operations (compound ops like split/remove)

Tool Categories:
    1. Structure: add_node, remove_node, split_node, refine_node, edit_node
    2. Execution: get_task, finish_task
    3. Query: list_nodes
"""

from collections.abc import Callable
from typing import Any

from cascade.storage.graph_storage import GraphStorage

__all__ = [
    # Structure operations
    "add_node",
    "remove_node",
    "split_node",
    "refine_node",
    "edit_node",
    # Execution operations
    "get_task",
    "finish_task",
    # Query operations
    "list_nodes",
    # Utilities
    "get_all_tools",
    "execute_tool",
]

# Type alias for tool functions
ToolFunc = Callable[[GraphStorage, dict[str, Any]], dict[str, Any]]


def get_all_tools() -> dict[str, ToolFunc]:
    """Get all available tools as a dictionary."""
    from tools import (
        add_node,
        edit_node,
        finish_task,
        get_task,
        list_nodes,
        refine_node,
        remove_node,
        split_node,
    )

    return {
        "add_node": add_node.add_node,
        "remove_node": remove_node.remove_node,
        "split_node": split_node.split_node,
        "refine_node": refine_node.refine_node,
        "edit_node": edit_node.edit_node,
        "get_task": get_task.get_task,
        "finish_task": finish_task.finish_task,
        "list_nodes": list_nodes.list_nodes,
    }


def execute_tool(storage: GraphStorage, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
    """Execute a tool by name.

    Raises:
        ValueError: If tool_name is not recognized.
    """
    tools = get_all_tools()
    if tool_name not in tools:
        available = ", ".join(tools.keys())
        raise ValueError(f"Unknown tool: {tool_name}. Available: {available}")

    return tools[tool_name](storage, params)
