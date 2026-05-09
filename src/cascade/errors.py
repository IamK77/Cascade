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

"""Cascade exception hierarchy.

All Cascade-specific exceptions inherit from CascadeError.
Client code can catch CascadeError for any framework error,
or catch specific subclasses for fine-grained handling.
"""


class CascadeError(Exception):
    """Base exception for all Cascade errors."""


class NodeNotFoundError(CascadeError):
    """Raised when a referenced node does not exist in the graph."""


class NodeExistsError(CascadeError):
    """Raised when adding a node that already exists."""


class CycleError(CascadeError):
    """Raised when an operation would create a cycle in the DAG."""


class InvalidTransitionError(CascadeError):
    """Raised when a state transition violates the state machine rules."""


class ContractError(CascadeError):
    """Raised when an edge contract is missing or incomplete."""


class LockError(CascadeError):
    """Raised when a storage lock cannot be acquired."""


class CancelledError(CascadeError):
    """Raised when an operation is cancelled."""

    def __init__(self, reason: str | None = None):
        self.reason = reason
        super().__init__(reason or "Operation cancelled")


class StorageCorruptionError(CascadeError):
    """Raised when stored data exists but cannot be deserialized.

    Distinct from "no data" (load returns None). Corruption means
    the file/record exists but its content is invalid — the caller
    must decide recovery strategy rather than silently treating it
    as an empty graph.
    """

    def __init__(
        self,
        reason: str,
        *,
        path: str | None = None,
    ):
        self.reason = reason
        self.path = path
        msg = f"Storage corruption: {reason}"
        if path:
            msg += f" ({path})"
        super().__init__(msg)
