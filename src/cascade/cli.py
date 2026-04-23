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

"""Cascade command-line interface.

Provides CLI access to all 11 tools. Output is JSON to stdout,
exit code 0 on success, 1 on failure.
"""

import argparse
import json
import sys
from typing import Any

from cascade.storage.graph_storage import GraphStorage
from tools import execute_tool


def get_storage(path: str = ".cascade") -> GraphStorage:
    return GraphStorage(path)


def output(result: dict[str, Any]) -> None:
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result.get("success", False) else 1)


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def cmd_add_node(args: argparse.Namespace) -> dict[str, Any]:
    deps = [d.strip() for d in (args.deps or "").split(",") if d.strip()]
    dependents = [d.strip() for d in (args.dependents or "").split(",") if d.strip()]
    params: dict[str, Any] = {"node_id": args.id, "dependencies": deps, "dependents": dependents}
    if args.expectations:
        try:
            params["expectations"] = json.loads(args.expectations)
        except json.JSONDecodeError:
            return {"success": False, "message": "Invalid JSON for --expectations"}
    return execute_tool(get_storage(args.storage), "add_node", params)


def cmd_get_task(args: argparse.Namespace) -> dict[str, Any]:
    params: dict[str, Any] = {"agent_id": args.agent}
    if args.task:
        params["task_id"] = args.task
    if args.timeout:
        params["timeout"] = args.timeout
    return execute_tool(get_storage(args.storage), "get_task", params)


def cmd_finish_task(args: argparse.Namespace) -> dict[str, Any]:
    params: dict[str, Any] = {"task_id": args.task}
    if args.success:
        params["success"] = True
        if args.summary:
            params["summary"] = args.summary
        if args.critical:
            try:
                params["critical"] = json.loads(args.critical)
            except json.JSONDecodeError:
                return {"success": False, "message": "Invalid JSON for --critical"}
        if args.artifacts:
            params["artifacts"] = args.artifacts
    elif args.fail:
        params["success"] = False
        if args.reason:
            params["summary"] = args.reason
        if args.cascade:
            params["cascade"] = True
    elif args.release:
        params["release"] = True
        if args.reason:
            params["summary"] = args.reason
    return execute_tool(get_storage(args.storage), "finish_task", params)


def cmd_list_nodes(args: argparse.Namespace) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if args.state:
        params["state_filter"] = args.state
    if args.pending_only:
        params["include_pending_only"] = True
    return execute_tool(get_storage(args.storage), "list_nodes", params)


def cmd_split_node(args: argparse.Namespace) -> dict[str, Any]:
    children = [c.strip() for c in args.children.split(",") if c.strip()]
    params: dict[str, Any] = {
        "parent_id": args.parent,
        "new_nodes": [{"node_id": cid} for cid in children],
    }
    if args.reason:
        params["reason"] = args.reason
    return execute_tool(get_storage(args.storage), "split_node", params)


def cmd_refine_node(args: argparse.Namespace) -> dict[str, Any]:
    params: dict[str, Any] = {"node_id": args.node, "dependency_id": args.dep}
    if args.expectation:
        params["expectation"] = args.expectation
    if args.promise:
        params["promise"] = args.promise
    if args.reason:
        params["reason"] = args.reason
    return execute_tool(get_storage(args.storage), "refine_node", params)


def cmd_remove_node(args: argparse.Namespace) -> dict[str, Any]:
    params: dict[str, Any] = {"node_id": args.node, "cascade": args.cascade}
    if args.reason:
        params["reason"] = args.reason
    return execute_tool(get_storage(args.storage), "remove_node", params)


def cmd_edit_node(args: argparse.Namespace) -> dict[str, Any]:
    params: dict[str, Any] = {"node_id": args.node}
    if args.state:
        params["state"] = args.state
    if args.summary:
        params["summary"] = args.summary
    if args.critical:
        try:
            params["critical"] = json.loads(args.critical)
        except json.JSONDecodeError:
            return {"success": False, "message": "Invalid JSON for --critical"}
    if args.artifacts:
        params["artifacts"] = args.artifacts
    if args.context_merge:
        params["context_merge"] = args.context_merge
    if args.reason:
        params["reason"] = args.reason
    return execute_tool(get_storage(args.storage), "edit_node", params)


def cmd_rework(args: argparse.Namespace) -> dict[str, Any]:
    params: dict[str, Any] = {
        "source_node_id": args.source,
        "corrective_node_id": args.corrective,
        "reason": args.reason,
        "agent_id": args.agent,
        "source_expectation": args.source_expectation,
        "source_promise": args.source_promise,
        "corrective_expectation": args.corrective_expectation,
        "corrective_promise": args.corrective_promise,
    }
    return execute_tool(get_storage(args.storage), "rework", params)


def cmd_check_task(args: argparse.Namespace) -> dict[str, Any]:
    return execute_tool(get_storage(args.storage), "check_task", {"task_id": args.task})


def cmd_check_timeouts(args: argparse.Namespace) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if args.default_timeout:
        params["default_timeout"] = args.default_timeout
    return execute_tool(get_storage(args.storage), "check_timeouts", params)


def cmd_history(args: argparse.Namespace) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if args.node:
        params["node_id"] = args.node
    if args.type:
        params["event_type"] = args.type
    if args.last:
        params["last_n"] = args.last
    if args.summary:
        params["summary"] = True
    return execute_tool(get_storage(args.storage), "history", params)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="cascade",
        description="Cascade — multi-agent task coordination via DAG",
    )
    parser.add_argument("--storage", "-s", default=".cascade", help="Storage directory")
    sub = parser.add_subparsers(dest="command", help="Commands")

    # add-node
    p = sub.add_parser("add-node", help="Create a task node")
    p.add_argument("--id", "-i", required=True, help="Node ID")
    p.add_argument("--deps", "-d", default="", help="Comma-separated dependency IDs")
    p.add_argument("--dependents", "-D", default="", help="Comma-separated dependent IDs")
    p.add_argument("--expectations", "-e", help="Contracts as JSON array")
    p.set_defaults(func=cmd_add_node)

    # get-task
    p = sub.add_parser("get-task", help="Claim a task (critical path priority)")
    p.add_argument("--agent", "-a", required=True, help="Agent ID")
    p.add_argument("--task", "-t", help="Specific task ID")
    p.add_argument("--timeout", type=float, help="Timeout in seconds")
    p.set_defaults(func=cmd_get_task)

    # finish-task
    p = sub.add_parser("finish-task", help="Complete, fail, or release a task")
    p.add_argument("--task", "-t", required=True, help="Task ID")
    p.add_argument("--success", action="store_true", help="Mark as completed")
    p.add_argument("--fail", action="store_true", help="Mark as failed")
    p.add_argument("--release", action="store_true", help="Release back to READY")
    p.add_argument("--summary", help="Summary for downstream")
    p.add_argument("--critical", help="Critical context as JSON")
    p.add_argument("--artifacts", help="Artifacts content")
    p.add_argument("--reason", help="Reason for fail/release")
    p.add_argument("--cascade", action="store_true", help="Cascade failure to dependents")
    p.set_defaults(func=cmd_finish_task)

    # list-nodes
    p = sub.add_parser("list-nodes", help="View all tasks")
    p.add_argument("--state", "-s", help="Filter by state")
    p.add_argument("--pending-only", action="store_true", help="Show only PENDING")
    p.set_defaults(func=cmd_list_nodes)

    # split-node
    p = sub.add_parser("split-node", help="Split a task into subtasks")
    p.add_argument("--parent", "-p", required=True, help="Parent node ID")
    p.add_argument("--children", "-c", required=True, help="Comma-separated child IDs")
    p.add_argument("--reason", help="Why this split is needed (recorded in event log)")
    p.set_defaults(func=cmd_split_node)

    # refine-node
    p = sub.add_parser("refine-node", help="Add dependency to a node")
    p.add_argument("--node", "-n", required=True, help="Node ID")
    p.add_argument("--dep", "-d", required=True, help="Dependency ID")
    p.add_argument("--expectation", help="What node expects from dep")
    p.add_argument("--promise", help="What dep promises to deliver")
    p.add_argument("--reason", help="Why this dependency is needed (recorded in event log)")
    p.set_defaults(func=cmd_refine_node)

    # remove-node
    p = sub.add_parser("remove-node", help="Remove a node")
    p.add_argument("--node", "-n", required=True, help="Node ID")
    p.add_argument("--cascade", action="store_true", help="Also remove dependents")
    p.add_argument("--reason", help="Why this node is being removed (recorded in event log)")
    p.set_defaults(func=cmd_remove_node)

    # edit-node
    p = sub.add_parser("edit-node", help="Update node properties")
    p.add_argument("--node", "-n", required=True, help="Node ID")
    p.add_argument("--state", help="New state")
    p.add_argument("--summary", help="Summary text")
    p.add_argument("--critical", help="Critical context as JSON")
    p.add_argument("--artifacts", help="Artifacts content")
    p.add_argument(
        "--context-merge", choices=["replace", "merge", "append"], help="How to merge context"
    )
    p.add_argument("--reason", help="Why this edit is needed (recorded in event log)")
    p.set_defaults(func=cmd_edit_node)

    # rework
    p = sub.add_parser("rework", help="Request upstream correction")
    p.add_argument("--source", required=True, help="Source node to correct")
    p.add_argument("--corrective", required=True, help="ID for corrective node")
    p.add_argument("--reason", required=True, help="Why rework is needed")
    p.add_argument("--agent", required=True, help="Agent requesting rework")
    p.add_argument(
        "--source-expectation", required=True, help="What corrective expects from source"
    )
    p.add_argument("--source-promise", required=True, help="What source promises")
    p.add_argument(
        "--corrective-expectation", required=True, help="What requester expects from correction"
    )
    p.add_argument("--corrective-promise", required=True, help="What corrective promises")
    p.set_defaults(func=cmd_rework)

    # check-task
    p = sub.add_parser(
        "check-task", help="Check if a task claim is still valid (pull cancellation)"
    )
    p.add_argument("--task", "-t", required=True, help="Task ID to check")
    p.set_defaults(func=cmd_check_task)

    # check-timeouts
    p = sub.add_parser("check-timeouts", help="Release stalled tasks")
    p.add_argument("--default-timeout", type=float, help="Default timeout in seconds")
    p.set_defaults(func=cmd_check_timeouts)

    # history
    p = sub.add_parser("history", help="Query event log")
    p.add_argument("--node", help="Filter by node ID")
    p.add_argument("--type", help="Filter by event type")
    p.add_argument("--last", type=int, help="Last N events")
    p.add_argument("--summary", action="store_true", help="Show counts by type")
    p.set_defaults(func=cmd_history)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    result = args.func(args)
    output(result)


def run() -> None:
    """Entry point for pyproject.toml scripts."""
    main()


if __name__ == "__main__":
    main()
