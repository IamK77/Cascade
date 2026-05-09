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

"""Typed Python client for Cascade.

The single API layer for all Cascade operations. All business logic
lives here — tools and CLI are thin wrappers that delegate to this.

    from cascade.client import CascadeClient, Contract

    cascade = CascadeClient()
    cascade.add("analyze")
    cascade.add("impl", deps={"analyze": Contract("Need spec", "Deliver code")})

    task = cascade.claim("worker-1")
    # task.id, task.upstream, task.promises ...
    cascade.complete(task.id, summary="Done", critical={"lang": "python"})
"""

from cascade.client.base import ClientBase
from cascade.client.execution import ExecutionMixin
from cascade.client.feedback import FeedbackMixin
from cascade.client.query import QueryMixin
from cascade.client.structure import StructureMixin
from cascade.types import Contract


class CascadeClient(
    StructureMixin,
    ExecutionMixin,
    FeedbackMixin,
    QueryMixin,
    ClientBase,
):
    """Typed Python client for Cascade.

    Composed from mixins — each handles a distinct responsibility:
    - ClientBase: transaction infrastructure, corruption recovery
    - StructureMixin: DAG structure (add, remove, split, refine, edit)
    - ExecutionMixin: task lifecycle (claim, complete, fail, release)
    - FeedbackMixin: feedback loop (rework)
    - QueryMixin: read-only queries (nodes, check, history, show, diff, snapshot_at)
    """


__all__ = ["CascadeClient", "Contract"]
