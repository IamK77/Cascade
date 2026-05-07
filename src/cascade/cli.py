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

Provides CLI access to all 11 tools via CascadeClient.
Output is JSON to stdout, exit code 0 on success, 1 on failure.
"""

import argparse
import json
import sys
from typing import Any

from cascade import __version__
from cascade.client import CascadeClient
from cascade.types import Contract, Result


def _result_to_dict(r: Result) -> dict[str, Any]:
    """Convert a Result to a dict for JSON output."""
    out: dict[str, Any] = {"success": r.success, "message": r.message, "data": r.data}
    if r.code:
        out["code"] = r.code
    return out


def output(result: dict[str, Any] | str) -> None:
    if isinstance(result, str):
        print(result)
        sys.exit(0)
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(0 if result.get("success", False) else 1)


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def cmd_add_node(args: argparse.Namespace) -> dict[str, Any]:
    client = CascadeClient(args.storage)
    dep_ids = [d.strip() for d in (args.deps or "").split(",") if d.strip()]
    dependent_ids = [d.strip() for d in (args.dependents or "").split(",") if d.strip()]

    # Parse expectations JSON into Contract dicts
    expectations_map: dict[str, dict[str, str]] = {}
    if args.expectations:
        try:
            expectations_list = json.loads(args.expectations)
        except json.JSONDecodeError:
            return {"success": False, "message": "Invalid JSON for --expectations"}
        for exp in expectations_list:
            exp_node_id = exp.get("node_id")
            expectation = exp.get("expectation")
            promise = exp.get("promise")
            if exp_node_id:
                if not expectation or not expectation.strip():
                    return {
                        "success": False,
                        "message": f"expectation is required for node '{exp_node_id}' in expectations",
                        "data": {},
                    }
                if not promise or not promise.strip():
                    return {
                        "success": False,
                        "message": f"promise is required for node '{exp_node_id}' in expectations",
                        "data": {},
                    }
                expectations_map[exp_node_id] = {"expectation": expectation, "promise": promise}

    # Validate contracts exist for all edges
    for dep_id in dep_ids:
        if dep_id not in expectations_map:
            return {
                "success": False,
                "message": (
                    f"Missing contract for dependency '{dep_id}'. "
                    f"Each dependency must have expectation and promise in 'expectations' parameter."
                ),
                "data": {"missing_contract_for": dep_id},
            }
    for dep_id in dependent_ids:
        if dep_id not in expectations_map:
            return {
                "success": False,
                "message": (
                    f"Missing contract for dependent '{dep_id}'. "
                    f"Each dependent must have expectation and promise in 'expectations' parameter."
                ),
                "data": {"missing_contract_for": dep_id},
            }

    deps = {
        dep_id: Contract(
            expectation=expectations_map[dep_id]["expectation"],
            promise=expectations_map[dep_id]["promise"],
        )
        for dep_id in dep_ids
    } or None

    dependents = {
        dep_id: Contract(
            expectation=expectations_map[dep_id]["expectation"],
            promise=expectations_map[dep_id]["promise"],
        )
        for dep_id in dependent_ids
    } or None

    r = client.add(args.id, deps=deps, dependents=dependents)
    return _result_to_dict(r)


def cmd_get_task(args: argparse.Namespace) -> dict[str, Any] | str:
    client = CascadeClient(args.storage)
    r = client.claim(
        args.agent,
        args.task if hasattr(args, "task") and args.task else None,
        timeout=args.timeout if hasattr(args, "timeout") and args.timeout else None,
    )
    if not r.success:
        return _result_to_dict(r)

    task_info = r.data.get("task_info", {})
    token = r.data.get("token")
    from cascade.view import render_briefing

    briefing = render_briefing(task_info)
    if token is not None:
        briefing += f"\n---\nfencing_token: {token}\n"
    return briefing


def cmd_finish_task(args: argparse.Namespace) -> dict[str, Any]:
    client = CascadeClient(args.storage)
    agent_id = args.agent if hasattr(args, "agent") and args.agent else None
    token = args.token if hasattr(args, "token") and args.token is not None else None

    if args.success:
        critical = None
        if args.critical:
            try:
                critical = json.loads(args.critical)
            except json.JSONDecodeError:
                return {"success": False, "message": "Invalid JSON for --critical"}
        r = client.complete(
            args.task,
            agent_id=agent_id,
            token=token,
            summary=args.summary or "",
            critical=critical,
            artifacts=args.artifacts or "",
        )
    elif args.fail:
        r = client.fail(
            args.task,
            agent_id=agent_id,
            token=token,
            reason=args.reason or "",
            cascade=args.cascade,
        )
    elif args.release:
        r = client.release(args.task, agent_id=agent_id, token=token, reason=args.reason or "")
    else:
        r = client.complete(args.task, agent_id=agent_id, token=token)

    return _result_to_dict(r)


def _parse_node_spec(
    item: dict[str, Any],
) -> tuple[str, dict[str, Contract] | None, dict[str, Contract] | None] | str:
    """Parse a single node spec from add-nodes batch JSON.

    Returns (node_id, deps, dependents) on success, error message string on failure.
    """
    node_id = item.get("id")
    if not node_id:
        return f"Missing 'id' in spec: {item}"

    dep_ids = item.get("deps", []) or []
    dependent_ids = item.get("dependents", []) or []

    expectations_map: dict[str, dict[str, str]] = {}
    for exp in item.get("expectations", []) or []:
        eid = exp.get("node_id")
        if not eid:
            continue
        e_text = exp.get("expectation")
        p_text = exp.get("promise")
        if not e_text or not e_text.strip():
            return f"expectation required for '{eid}' in node '{node_id}'"
        if not p_text or not p_text.strip():
            return f"promise required for '{eid}' in node '{node_id}'"
        expectations_map[eid] = {"expectation": e_text, "promise": p_text}

    for dep_id in dep_ids:
        if dep_id not in expectations_map:
            return f"Missing contract for dependency '{dep_id}' in node '{node_id}'"
    for dep_id in dependent_ids:
        if dep_id not in expectations_map:
            return f"Missing contract for dependent '{dep_id}' in node '{node_id}'"

    deps = {
        dep_id: Contract(
            expectation=expectations_map[dep_id]["expectation"],
            promise=expectations_map[dep_id]["promise"],
        )
        for dep_id in dep_ids
    } or None
    dependents = {
        dep_id: Contract(
            expectation=expectations_map[dep_id]["expectation"],
            promise=expectations_map[dep_id]["promise"],
        )
        for dep_id in dependent_ids
    } or None
    return node_id, deps, dependents


def cmd_add_nodes(args: argparse.Namespace) -> dict[str, Any]:
    if args.file:
        try:
            with open(args.file) as f:
                raw = f.read()
        except OSError as e:
            return {"success": False, "message": f"Cannot read --file: {e}"}
    else:
        raw = args.json or ""

    if not raw.strip():
        return {"success": False, "message": "Pass --json '<array>' or --file <path>"}

    try:
        items = json.loads(raw)
    except json.JSONDecodeError as e:
        return {"success": False, "message": f"Invalid JSON: {e}"}

    if not isinstance(items, list):
        return {"success": False, "message": "Top-level JSON must be a list of node specs"}

    specs: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            return {"success": False, "message": f"Each item must be an object, got: {item}"}
        parsed = _parse_node_spec(item)
        if isinstance(parsed, str):
            return {"success": False, "message": parsed}
        nid, deps, dependents = parsed
        specs.append({"node_id": nid, "deps": deps, "dependents": dependents})

    client = CascadeClient(args.storage)
    r = client.add_batch(specs)
    return _result_to_dict(r)


def cmd_watch(args: argparse.Namespace) -> None:
    """Stream node state transitions to stdout as JSONL.

    Watches graph.json directly via mtime polling. On each change,
    diffs current vs previous snapshot and emits one transition per
    node whose state changed. Initial snapshot is the baseline — no
    transitions emitted at startup. Press Ctrl-C to exit.
    """
    import time as _t
    from pathlib import Path

    # Defense-in-depth: when stdout is a pipe Python defaults to block-buffering.
    # Per-print flush=True handles the common case; line_buffering ensures any
    # forgotten path still flushes on newline so consumers see lines immediately.
    sys.stdout.reconfigure(line_buffering=True)  # type: ignore[union-attr]

    graph_path = Path(args.storage) / "graph.json"

    def read_snapshot() -> dict[str, dict[str, Any]] | None:
        try:
            data = json.loads(graph_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return None
        result: dict[str, dict[str, Any]] = {}
        for nid, node in (data.get("nodes") or {}).items():
            entry: dict[str, Any] = {"state": node.get("state")}
            if node.get("agent_id"):
                entry["agent_id"] = node["agent_id"]
            result[nid] = entry
        return result

    def emit(transition: dict[str, Any]) -> None:
        print(json.dumps(transition, ensure_ascii=False), flush=True)

    last_mtime = 0.0
    last_snapshot: dict[str, dict[str, Any]] = {}

    if graph_path.exists():
        last_mtime = graph_path.stat().st_mtime
        snap = read_snapshot()
        if snap is not None:
            last_snapshot = snap

    try:
        while True:
            try:
                mtime = graph_path.stat().st_mtime if graph_path.exists() else 0.0
            except OSError:
                mtime = 0.0

            if mtime == last_mtime:
                _t.sleep(0.05)
                continue

            snap = read_snapshot()
            if snap is None:
                _t.sleep(0.05)
                continue

            last_mtime = mtime
            now = _t.time()
            has_changes = False

            for nid, entry in snap.items():
                prev = last_snapshot.get(nid)
                if prev is None:
                    transition: dict[str, Any] = {
                        "type": "transition",
                        "node": nid,
                        "from": None,
                        "to": entry["state"],
                        "ts": now,
                    }
                    if entry.get("agent_id"):
                        transition["agent"] = entry["agent_id"]
                    emit(transition)
                    has_changes = True
                elif prev["state"] != entry["state"]:
                    transition = {
                        "type": "transition",
                        "node": nid,
                        "from": prev["state"],
                        "to": entry["state"],
                        "ts": now,
                    }
                    if entry.get("agent_id"):
                        transition["agent"] = entry["agent_id"]
                    emit(transition)
                    has_changes = True

            for nid, prev in last_snapshot.items():
                if nid not in snap:
                    emit(
                        {
                            "type": "transition",
                            "node": nid,
                            "from": prev["state"],
                            "to": None,
                            "ts": now,
                        }
                    )
                    has_changes = True

            ready = [nid for nid, entry in snap.items() if entry["state"] == "READY"]
            if has_changes:
                emit({"type": "ready", "nodes": ready, "ts": now})

            last_snapshot = snap
    except KeyboardInterrupt:
        return


def cmd_inspect(args: argparse.Namespace) -> dict[str, Any] | str:
    from cascade.core.cascade import Cascade
    from cascade.view import render_inspect

    client = CascadeClient(args.storage)
    with client._storage.lock():
        graph = client._storage.load() or Cascade()
        if args.task not in graph.nodes:
            return {"success": False, "message": f"Task {args.task} not found"}
        return render_inspect(graph, args.task)


def cmd_list_nodes(args: argparse.Namespace) -> dict[str, Any]:
    client = CascadeClient(args.storage)
    r = client.nodes(
        state=args.state if hasattr(args, "state") and args.state else None,
        include_pending_only=args.pending_only if hasattr(args, "pending_only") else False,
    )
    return _result_to_dict(r)


def cmd_split_node(args: argparse.Namespace) -> dict[str, Any]:
    client = CascadeClient(args.storage)
    children = [c.strip() for c in args.children.split(",") if c.strip()]
    r = client.split(
        args.parent,
        children,
        reason=args.reason or "",
    )
    return _result_to_dict(r)


def cmd_refine_node(args: argparse.Namespace) -> dict[str, Any]:
    client = CascadeClient(args.storage)
    r = client.refine(
        args.node,
        args.dep,
        args.expectation or "",
        args.promise or "",
        reason=args.reason or "",
    )
    return _result_to_dict(r)


def cmd_remove_node(args: argparse.Namespace) -> dict[str, Any]:
    client = CascadeClient(args.storage)
    r = client.remove(
        args.node,
        cascade=args.cascade,
        reason=args.reason or "",
    )
    return _result_to_dict(r)


def cmd_edit_node(args: argparse.Namespace) -> dict[str, Any]:
    client = CascadeClient(args.storage)
    critical = None
    if args.critical:
        try:
            critical = json.loads(args.critical)
        except json.JSONDecodeError:
            return {"success": False, "message": "Invalid JSON for --critical"}
    r = client.edit(
        args.node,
        state=args.state or "",
        summary=args.summary or "",
        critical=critical,
        artifacts=args.artifacts or "",
        context_merge=args.context_merge or "merge",
        reason=args.reason or "",
    )
    return _result_to_dict(r)


def cmd_rework(args: argparse.Namespace) -> dict[str, Any]:
    client = CascadeClient(args.storage)
    r = client.rework(
        args.source,
        args.corrective,
        args.reason,
        args.agent,
        source_expectation=args.source_expectation,
        source_promise=args.source_promise,
        corrective_expectation=args.corrective_expectation,
        corrective_promise=args.corrective_promise,
    )
    return _result_to_dict(r)


def cmd_check_task(args: argparse.Namespace) -> dict[str, Any]:
    client = CascadeClient(args.storage)
    r = client.check(args.task)
    return _result_to_dict(r)


def cmd_check_timeouts(args: argparse.Namespace) -> dict[str, Any]:
    client = CascadeClient(args.storage)
    r = client.check_timeouts(
        default_timeout=args.default_timeout
        if hasattr(args, "default_timeout") and args.default_timeout
        else None,
    )
    return _result_to_dict(r)


def cmd_history(args: argparse.Namespace) -> dict[str, Any]:
    client = CascadeClient(args.storage)
    r = client.history(
        node_id=args.node or "",
        event_type=args.type or "",
        last_n=args.last or 0,
        summary=args.summary if hasattr(args, "summary") else False,
    )
    return _result_to_dict(r)


def cmd_show(args: argparse.Namespace) -> dict[str, Any]:
    client = CascadeClient(args.storage)
    r = client.show(args.ts)
    return _result_to_dict(r)


def cmd_diff(args: argparse.Namespace) -> dict[str, Any]:
    client = CascadeClient(args.storage)
    r = client.diff(args.from_ts, args.to_ts)
    return _result_to_dict(r)


def cmd_snapshot_at(args: argparse.Namespace) -> dict[str, Any]:
    client = CascadeClient(args.storage)
    r = client.snapshot_at(args.ts)
    return _result_to_dict(r)


def cmd_verify_chain(args: argparse.Namespace) -> dict[str, Any]:
    client = CascadeClient(args.storage)
    event_count = client.storage.events.count
    valid, msg = client.storage.events.verify_chain()
    if valid:
        return {
            "success": True,
            "message": f"Hash chain valid: {event_count} events verified",
            "data": {"events_verified": event_count},
        }
    return {
        "success": False,
        "message": msg,
        "data": {"events_total": event_count},
    }


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="cascade",
        description="Cascade — multi-agent task coordination via DAG",
    )
    parser.add_argument("--version", "-V", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--storage", "-s", default=".cascade", help="Storage directory")
    sub = parser.add_subparsers(dest="command", help="Commands")

    # add-node
    p = sub.add_parser("add-node", help="Create a task node")
    p.add_argument("--id", "-i", required=True, help="Node ID")
    p.add_argument("--deps", "-d", default="", help="Comma-separated dependency IDs")
    p.add_argument("--dependents", "-D", default="", help="Comma-separated dependent IDs")
    p.add_argument("--expectations", "-e", help="Contracts as JSON array")
    p.set_defaults(func=cmd_add_node)

    # add-nodes (batch)
    p = sub.add_parser(
        "add-nodes",
        help="Create multiple task nodes atomically (single lock, single save)",
    )
    p.add_argument("--json", help="Inline JSON array of node specs")
    p.add_argument("--file", "-f", help="Path to JSON file with node specs")
    p.set_defaults(func=cmd_add_nodes)

    # get-task
    p = sub.add_parser("get-task", help="Claim a task (critical path priority)")
    p.add_argument("--agent", "-a", required=True, help="Agent ID")
    p.add_argument("--task", "-t", help="Specific task ID")
    p.add_argument("--timeout", type=float, help="Timeout in seconds")
    p.set_defaults(func=cmd_get_task)

    # finish-task
    p = sub.add_parser("finish-task", help="Complete, fail, or release a task")
    p.add_argument("--task", "-t", required=True, help="Task ID")
    p.add_argument("--agent", "-a", help="Agent ID (must match the claiming agent)")
    p.add_argument("--token", type=int, help="Fencing token from get-task (rejects stale writes)")
    p.add_argument("--success", action="store_true", help="Mark as completed")
    p.add_argument("--fail", action="store_true", help="Mark as failed")
    p.add_argument("--release", action="store_true", help="Release back to READY")
    p.add_argument("--summary", help="Summary for downstream")
    p.add_argument("--critical", help="Critical context as JSON")
    p.add_argument("--artifacts", help="Artifacts content")
    p.add_argument("--reason", help="Reason for fail/release")
    p.add_argument("--cascade", action="store_true", help="Cascade failure to dependents")
    p.set_defaults(func=cmd_finish_task)

    # inspect
    p = sub.add_parser(
        "inspect", help="Read-only review of a task's briefing and delivered context"
    )
    p.add_argument("--task", "-t", required=True, help="Task ID to inspect")
    p.set_defaults(func=cmd_inspect)

    # watch
    p = sub.add_parser(
        "watch",
        help="Stream node state transitions to stdout as JSONL (long-running)",
    )
    p.set_defaults(func=cmd_watch)

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

    # show
    p = sub.add_parser("show", help="Show event at a logical timestamp")
    p.add_argument("--ts", type=int, required=True, help="Logical timestamp")
    p.set_defaults(func=cmd_show)

    # diff
    p = sub.add_parser("diff", help="Show events between two logical timestamps")
    p.add_argument("--from", type=int, required=True, dest="from_ts", help="Start logical_ts")
    p.add_argument("--to", type=int, required=True, dest="to_ts", help="End logical_ts")
    p.set_defaults(func=cmd_diff)

    # snapshot-at
    p = sub.add_parser("snapshot-at", help="Rebuild graph state at a logical timestamp")
    p.add_argument("--ts", type=int, required=True, help="Logical timestamp to replay to")
    p.set_defaults(func=cmd_snapshot_at)

    # verify-chain
    p = sub.add_parser("verify-chain", help="Verify event log hash chain integrity")
    p.set_defaults(func=cmd_verify_chain)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    result = args.func(args)
    if result is None:
        # Streaming/long-running commands (e.g. watch) print directly and
        # return None on clean exit; nothing to format.
        sys.exit(0)
    output(result)


def run() -> None:
    """Entry point for pyproject.toml scripts."""
    main()


if __name__ == "__main__":
    main()
