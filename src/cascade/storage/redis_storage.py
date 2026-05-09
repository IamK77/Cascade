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

"""Redis-backed storage for distributed Cascade deployments.

Requires the ``redis`` optional dependency::

    pip install cascade-auto[redis]

All sub-components share a single Redis connection and a key prefix
so multiple Cascade instances can coexist in the same Redis database.

Key layout (prefix = ``cascade:{namespace}``)::

    {prefix}:graph              JSON string   — serialized graph
    {prefix}:lamport            int           — HLC counter
    {prefix}:events             List[JSON]    — append-only event log
    {prefix}:events:last_hash   string        — chain integrity tail
    {prefix}:tokens:{node_id}   JSON string   — token status
    {prefix}:ops                Hash          — op_id → JSON result
    {prefix}:blobs:{ref}        string        — content blobs
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any, cast

from cascade.core.cascade import Cascade
from cascade.errors import LockError, StorageCorruptionError
from cascade.events import Event, EventType, _compute_hash
from cascade.storage._serde import deserialize_graph, serialize_graph
from cascade.storage.content import ContentStore
from cascade.storage.protocol import (
    EventStoreProtocol,
    EventStoreQueries,
    OpLogProtocol,
    TokenStoreProtocol,
)
from cascade.storage.token_store import CancelNotifier
from cascade.types import TokenStatus

# redis-py 6.x types all commands as -> ResponseT (= Awaitable[Any] | Any)
# because the same class tree backs both sync Redis and async AsyncRedis.
# There is no way to parametrize it to "sync str-only" at the type level.
# We type the client as Any and enforce correctness at our API boundary.
_Redis = Any

# Lua script: atomic HLC advance.
# KEYS[1] = lamport key, ARGV[1] = physical_ms
# Returns the new lamport value.
_LUA_NEXT_LAMPORT = """
local current = tonumber(redis.call('GET', KEYS[1]) or '0') or 0
local physical = tonumber(ARGV[1])
local new_val = math.max(physical, current) + 1
redis.call('SET', KEYS[1], tostring(new_val))
return tostring(new_val)
"""

# Lua script: atomic observe (advance only if remote > current).
# KEYS[1] = lamport key, ARGV[1] = remote_ts
_LUA_OBSERVE = """
local current = tonumber(redis.call('GET', KEYS[1]) or '0') or 0
local remote = tonumber(ARGV[1])
if remote > current then
    redis.call('SET', KEYS[1], tostring(remote))
end
"""


def _require_redis() -> type:
    try:
        import redis

        return redis.Redis
    except ImportError:
        raise ImportError(
            "RedisStorage requires the 'redis' package. "
            "Install it with: pip install cascade-auto[redis]"
        ) from None


# ---------------------------------------------------------------------------
# Sub-components
# ---------------------------------------------------------------------------


class RedisEventStore(EventStoreQueries):
    """Append-only event log backed by a Redis List.

    Callers must hold the storage lock when emitting events — the hash
    chain requires serial access (same contract as FileEventStore).
    """

    def __init__(self, r: _Redis, prefix: str) -> None:
        self._r = r
        self._events_key = f"{prefix}:events"
        self._hash_key = f"{prefix}:events:last_hash"

    def _last_hash(self) -> str:
        val = self._r.get(self._hash_key)
        return cast(str, val) if val is not None else ""

    def emit(
        self, event_type: EventType, logical_ts: int, *, trace_id: str = "", **data: Any
    ) -> Event:
        event_id = uuid.uuid4().hex
        timestamp = time.time()
        content: dict[str, Any] = {
            "id": event_id,
            "type": event_type.value,
            "timestamp": timestamp,
            "logical_ts": logical_ts,
            "data": data,
        }
        if trace_id:
            content["trace_id"] = trace_id

        prev_hash = self._last_hash()
        event_hash = _compute_hash(content, prev_hash)

        event = Event(
            type=event_type,
            timestamp=timestamp,
            id=event_id,
            logical_ts=logical_ts,
            data=data,
            trace_id=trace_id,
            prev_hash=prev_hash,
            hash=event_hash,
        )

        pipe = self._r.pipeline()
        pipe.rpush(self._events_key, json.dumps(event.to_dict(), ensure_ascii=False))
        pipe.set(self._hash_key, event_hash)
        pipe.execute()
        return event

    def read_all(self) -> list[Event]:
        raw = cast(list[str], self._r.lrange(self._events_key, 0, -1))
        return [Event.from_dict(json.loads(item)) for item in raw]

    def clear(self) -> None:
        self._r.delete(self._events_key, self._hash_key)

    @property
    def count(self) -> int:
        return cast(int, self._r.llen(self._events_key))

    def verify_chain(self) -> tuple[bool, str]:
        events = self.read_all()
        prev_hash = ""
        for i, event in enumerate(events):
            if not event.hash:
                continue
            if event.prev_hash != prev_hash:
                return False, (
                    f"Event #{i} (logical_ts={event.logical_ts}): "
                    f"prev_hash mismatch — expected {prev_hash[:12]}..., "
                    f"got {event.prev_hash[:12]}..."
                )
            content: dict[str, Any] = {
                "id": event.id,
                "type": event.type.value,
                "timestamp": event.timestamp,
                "logical_ts": event.logical_ts,
                "data": event.data,
            }
            if event.trace_id:
                content["trace_id"] = event.trace_id
            expected = _compute_hash(content, prev_hash)
            if event.hash != expected:
                return False, (
                    f"Event #{i} (logical_ts={event.logical_ts}): "
                    f"hash mismatch — content was tampered"
                )
            prev_hash = event.hash
        return True, ""


class RedisTokenStore:
    """Task claim token storage backed by Redis keys."""

    def __init__(self, r: _Redis, prefix: str) -> None:
        self._r = r
        self._prefix = prefix
        self._notifiers: dict[str, CancelNotifier] = {}

    def _key(self, node_id: str) -> str:
        return f"{self._prefix}:tokens:{node_id}"

    def create(
        self,
        node_id: str,
        agent_id: str,
        claimed_at: float,
        notifier: CancelNotifier | None = None,
    ) -> TokenStatus:
        token = TokenStatus(
            node_id=node_id,
            agent_id=agent_id,
            valid=True,
            claimed_at=claimed_at,
        )
        self._r.set(self._key(node_id), json.dumps(token.to_dict(), ensure_ascii=False))
        if notifier is not None:
            self._notifiers[node_id] = notifier
        return token

    def check(self, node_id: str) -> TokenStatus | None:
        raw = self._r.get(self._key(node_id))
        if raw is None:
            return None
        return TokenStatus.from_dict(json.loads(cast(str, raw)))

    def invalidate(self, node_id: str, reason: str) -> TokenStatus | None:
        token = self.check(node_id)
        if token is None or not token.valid:
            return token

        token.valid = False
        token.reason = reason
        token.invalidated_at = time.time()

        self._r.set(self._key(node_id), json.dumps(token.to_dict(), ensure_ascii=False))

        notifier = self._notifiers.pop(node_id, None)
        if notifier is not None:
            notifier.notify(token)

        return token

    def cleanup(self, node_id: str) -> None:
        self._r.delete(self._key(node_id))
        self._notifiers.pop(node_id, None)


class RedisOpLog:
    """Idempotent operation log backed by a Redis Hash."""

    def __init__(self, r: _Redis, prefix: str) -> None:
        self._r = r
        self._key = f"{prefix}:ops"

    def get(self, op_id: str) -> dict[str, Any] | None:
        raw = self._r.hget(self._key, op_id)
        if raw is None:
            return None
        result: dict[str, Any] = json.loads(cast(str, raw))
        return result

    def record(self, op_id: str, result: dict[str, Any]) -> None:
        self._r.hset(self._key, op_id, json.dumps(result, ensure_ascii=False))


class RedisContentStore:
    """Content-addressable blob storage backed by Redis keys."""

    def __init__(self, r: _Redis, prefix: str) -> None:
        self._r = r
        self._prefix = prefix

    def _key(self, ref: str) -> str:
        return f"{self._prefix}:blobs:{ref}"

    def put(self, content: str) -> str:
        ref = hashlib.sha256(content.encode("utf-8")).hexdigest()
        self._r.setnx(self._key(ref), content)
        return ref

    def get(self, ref: str) -> str | None:
        val = self._r.get(self._key(ref))
        return cast(str, val) if val is not None else None

    def exists(self, ref: str) -> bool:
        return bool(self._r.exists(self._key(ref)))


# ---------------------------------------------------------------------------
# Top-level storage
# ---------------------------------------------------------------------------


class RedisStorage:
    """Redis-backed Cascade persistence implementing StorageProtocol.

    Uses a key prefix (``cascade:{namespace}``) so multiple Cascade
    instances can share a single Redis database.
    """

    def __init__(
        self,
        redis_client: _Redis = None,
        *,
        namespace: str = "default",
        lock_timeout: float = 30.0,
        url: str | None = None,
    ) -> None:
        if redis_client is not None:
            self._r: _Redis = redis_client
        elif url is not None:
            redis_cls: Any = _require_redis()
            self._r = redis_cls.from_url(url, decode_responses=True)
        else:
            redis_cls_: Any = _require_redis()
            self._r = redis_cls_(decode_responses=True)

        self._prefix = f"cascade:{namespace}"
        self._lock_timeout = lock_timeout
        self._lua_next_lamport = self._r.register_script(_LUA_NEXT_LAMPORT)
        self._lua_observe = self._r.register_script(_LUA_OBSERVE)

        self.events: EventStoreProtocol = RedisEventStore(self._r, self._prefix)
        self.tokens: TokenStoreProtocol = RedisTokenStore(self._r, self._prefix)
        self.ops: OpLogProtocol = RedisOpLog(self._r, self._prefix)
        self.content: ContentStore = RedisContentStore(self._r, self._prefix)

    # -- Lamport / HLC -----------------------------------------------------

    def _lamport_key(self) -> str:
        return f"{self._prefix}:lamport"

    def next_lamport(self) -> int:
        physical_ms = int(time.time() * 1000)
        result = self._lua_next_lamport(keys=[self._lamport_key()], args=[physical_ms])
        return int(result)

    def observe(self, remote_ts: int) -> None:
        self._lua_observe(keys=[self._lamport_key()], args=[remote_ts])

    # -- Lock --------------------------------------------------------------

    @contextmanager
    def lock(self, timeout: float = 10.0, blocking: bool = True) -> Generator[None, None, None]:
        redis_lock = self._r.lock(f"{self._prefix}:lock", timeout=self._lock_timeout)
        acquired = redis_lock.acquire(
            blocking=blocking,
            blocking_timeout=timeout if blocking else None,
        )
        if not acquired:
            raise LockError(
                f"Could not acquire Redis lock within {timeout} seconds"
                if blocking
                else "Could not acquire Redis lock: another holder"
            )
        try:
            yield
        finally:
            try:
                redis_lock.release()
            except Exception:
                pass

    # -- Graph persistence -------------------------------------------------

    def _graph_key(self) -> str:
        return f"{self._prefix}:graph"

    def exists(self) -> bool:
        return bool(self._r.exists(self._graph_key()))

    def save(self, cascade: Cascade) -> None:
        lamport_val = self._r.get(self._lamport_key())
        lamport = int(lamport_val) if lamport_val else 0
        graph_data = serialize_graph(cascade, lamport, self.content)
        self._r.set(self._graph_key(), json.dumps(graph_data, ensure_ascii=False))

    def load(self) -> Cascade | None:
        raw = self._r.get(self._graph_key())
        if raw is None:
            return None

        try:
            graph_data = json.loads(cast(str, raw))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise StorageCorruptionError(
                "malformed data in Redis graph key",
                path=self._graph_key(),
            ) from e

        if not isinstance(graph_data, dict):
            raise StorageCorruptionError(
                f"expected JSON object, got {type(graph_data).__name__}",
                path=self._graph_key(),
            )

        try:
            cascade, stored_lamport = deserialize_graph(graph_data, self.content)
        except (KeyError, AttributeError, TypeError, ValueError) as e:
            raise StorageCorruptionError(
                f"invalid graph structure: {e}",
                path=self._graph_key(),
            ) from e

        self._r.set(self._lamport_key(), stored_lamport)
        return cascade

    def backup_corrupt(self) -> str | None:
        """Copy corrupt graph data to a backup key for forensics."""
        graph_key = f"{self._prefix}:graph"
        raw = self._r.get(graph_key)
        if raw is None:
            return None
        backup_key = f"{graph_key}:corrupt:{time.time_ns()}"
        self._r.set(backup_key, raw)
        self._r.delete(graph_key)
        return backup_key

    def delete(self) -> None:
        cursor: int = 0
        pattern = f"{self._prefix}:*"
        while True:
            cursor, keys = self._r.scan(cursor=cursor, match=pattern, count=100)
            if keys:
                self._r.delete(*keys)
            if cursor == 0:
                break
