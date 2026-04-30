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

"""Storage protocol — the interface any Cascade backend must implement."""

from collections.abc import Generator
from contextlib import contextmanager
from typing import Protocol, runtime_checkable

from cascade.core.cascade import Cascade
from cascade.events import EventStore
from cascade.storage.token_store import TokenStore


@runtime_checkable
class StorageProtocol(Protocol):
    """Interface for Cascade persistence backends.

    FileStorage is the built-in implementation (JSON + filelock).
    Distributed backends (etcd, Postgres, etc.) implement this
    same protocol.
    """

    events: EventStore
    tokens: TokenStore

    def exists(self) -> bool: ...

    @contextmanager
    def lock(self, timeout: float = 10.0, blocking: bool = True) -> Generator[None, None, None]: ...

    def load(self) -> Cascade | None: ...

    def save(self, cascade: Cascade) -> None: ...

    def delete(self) -> None: ...
