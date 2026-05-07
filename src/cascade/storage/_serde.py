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

"""Graph serialization — shared between FileStorage and RedisStorage."""

from __future__ import annotations

from typing import Any

from cascade.core.cascade import Cascade
from cascade.core.node import Node
from cascade.core.state import NodeState
from cascade.storage.content import ContentStore
from cascade.types import Context, Contract, Provenance


def serialize_graph(cascade: Cascade, lamport: int, content: ContentStore) -> dict[str, Any]:
    """Serialize a Cascade graph to a JSON-compatible dict."""
    graph_data: dict[str, Any] = {
        "epoch": cascade.epoch,
        "lamport": lamport,
        "nodes": {},
        "edges": [],
    }

    for node_id, node in cascade.nodes.items():
        node_data: dict[str, Any] = {
            "id": node.id,
            "state": node.state.name,
        }

        if node.agent_id:
            node_data["agent_id"] = node.agent_id
        if node.claimed_at is not None:
            node_data["claimed_at"] = node.claimed_at
        if node.timeout is not None:
            node_data["timeout"] = node.timeout

        if node.context:
            ctx_data: dict[str, Any] = {}
            if node.context.critical:
                ctx_data["critical"] = node.context.critical
            if node.context.summary:
                ctx_data["summary"] = node.context.summary
            if node.context.artifacts:
                ref = content.put(node.context.artifacts)
                ctx_data["artifacts_ref"] = ref
            if node.context.provenance:
                ctx_data["provenance"] = node.context.provenance.to_dict()
            if ctx_data:
                node_data["context"] = ctx_data

        graph_data["nodes"][node_id] = node_data

    for (from_id, to_id), contract in cascade.contracts.items():
        graph_data["edges"].append(
            {
                "from": from_id,
                "to": to_id,
                "expectation": contract.expectation,
                "promise": contract.promise,
            }
        )

    return graph_data


def deserialize_graph(graph_data: dict[str, Any], content: ContentStore) -> tuple[Cascade, int]:
    """Deserialize a dict into a Cascade graph. Returns (cascade, lamport)."""
    cascade = Cascade()
    cascade.epoch = graph_data.get("epoch", 0)
    lamport = graph_data.get("lamport", 0)

    for node_id, node_data in graph_data.get("nodes", {}).items():
        state = NodeState[node_data.get("state", "PENDING")]
        agent_id = node_data.get("agent_id")

        context = None
        if "context" in node_data:
            ctx_data = node_data["context"]
            artifacts = ""

            artifacts_ref = ctx_data.get("artifacts_ref", "")
            if artifacts_ref:
                artifacts = content.get(artifacts_ref) or ""

            prov_data = ctx_data.get("provenance")
            provenance = Provenance.from_dict(prov_data) if prov_data else None

            context = Context(
                critical=ctx_data.get("critical", {}),
                summary=ctx_data.get("summary", ""),
                artifacts=artifacts,
                provenance=provenance,
            )

        node = Node(
            id=node_id,
            state=state,
            context=context,
            agent_id=agent_id,
            claimed_at=node_data.get("claimed_at"),
            timeout=node_data.get("timeout"),
        )
        cascade.add_node(node)

    for edge in graph_data.get("edges", []):
        from_id = edge.get("from")
        to_id = edge.get("to")
        expectation = edge.get("expectation", "")
        promise = edge.get("promise", "")

        if from_id in cascade.nodes and to_id in cascade.nodes:
            cascade.restore_edge(
                from_id,
                to_id,
                Contract(expectation=expectation, promise=promise),
            )

    return cascade, lamport
