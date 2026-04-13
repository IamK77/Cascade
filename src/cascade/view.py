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

"""Node view construction — presentation layer.

Builds the dict that an LLM agent receives when it claims a task.
This is separated from Cascade because it's presentation concern,
not a graph primitive.
"""

from collections import deque
from typing import Any

from cascade.context.propagator import ContextPropagator
from cascade.core.cascade import Cascade


def get_node_view(cascade: Cascade, node_id: str) -> dict[str, Any]:
    """Get all information an agent needs to execute a node.

    Composes data from multiple sources:
    - Merged upstream context (via ContextPropagator)
    - Edge contracts (expectations from dependencies)
    - Promises to downstream dependents
    - Visible descendant topology (2 hops)
    """
    if node_id not in cascade.nodes:
        raise ValueError(f"Node {node_id} not found")

    node = cascade.nodes[node_id]

    propagator = ContextPropagator(cascade)
    merged_context = propagator.collect_context_at(node_id)

    context_dict: dict[str, Any] = {}
    if merged_context.critical:
        context_dict["critical"] = merged_context.critical
    if merged_context.summary:
        context_dict["summary"] = merged_context.summary
    if merged_context.artifacts:
        context_dict["artifacts"] = merged_context.artifacts

    contracts = []
    for dep_info in cascade.get_node_dependencies_info(node_id):
        contract_dict: dict[str, Any] = {"node_id": dep_info["node_id"]}
        if dep_info["expectation"]:
            contract_dict["expectation"] = dep_info["expectation"]
        if dep_info["promise"]:
            contract_dict["promise"] = dep_info["promise"]
        contracts.append(contract_dict)

    promises = cascade.get_node_promises(node_id)
    visible_descendants = _get_visible_descendants(cascade, node_id, max_distance=2)

    result: dict[str, Any] = {"id": node.id, "state": node.state.name}
    if context_dict:
        result["context"] = context_dict
    if contracts:
        result["contracts"] = contracts
    if promises:
        result["promises"] = promises
    if visible_descendants:
        result["visible_nodes"] = visible_descendants

    return result


def _get_visible_descendants(
    cascade: Cascade, node_id: str, max_distance: int = 2
) -> dict[str, Any]:
    """Get visible descendant nodes within specified distance."""
    result: dict[str, Any] = {}
    visited: dict[str, int] = {node_id: 0}
    queue = deque([(node_id, 0)])

    while queue:
        current_id, distance = queue.popleft()
        if distance < max_distance:
            for dependent in cascade.get_dependents(current_id):
                if dependent.id not in visited:
                    visited[dependent.id] = distance + 1
                    queue.append((dependent.id, distance + 1))

        if distance == 0 or distance > max_distance:
            continue

        current_node = cascade.nodes[current_id]
        node_info: dict[str, Any] = {"id": current_node.id, "state": current_node.state.name}

        expectations = []
        for dep_info in cascade.get_node_dependencies_info(current_id):
            expect_info: dict[str, Any] = {"node_id": dep_info["node_id"]}
            if dep_info["expectation"]:
                expect_info["expectation"] = dep_info["expectation"]
            if dep_info["promise"]:
                expect_info["promise"] = dep_info["promise"]
            expectations.append(expect_info)
        if expectations:
            node_info["expectations"] = expectations

        distance_key = str(distance)
        if distance_key not in result:
            result[distance_key] = []
        result[distance_key].append(node_info)

    return result
