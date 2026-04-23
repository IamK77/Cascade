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

"""Tests for TokenStore, CancelNotifier, and ACTIVE node protection."""

import time

from cascade.context.cancellation import CancellationToken
from cascade.storage.token_store import (
    CallbackNotifier,
    CancelNotifier,
    FileNotifier,
)
from tools import add_node, check_task, finish_task, get_task, remove_node, split_node


class TestTokenStore:
    """Tests for TokenStore lifecycle."""

    def test_create_and_check(self, temp_storage):
        store = temp_storage.tokens
        token = store.create("task-a", "agent-1", time.time())
        assert token.valid
        assert token.agent_id == "agent-1"

        checked = store.check("task-a")
        assert checked is not None
        assert checked.valid
        assert checked.node_id == "task-a"

    def test_check_nonexistent(self, temp_storage):
        assert temp_storage.tokens.check("nonexistent") is None

    def test_invalidate(self, temp_storage):
        store = temp_storage.tokens
        store.create("task-a", "agent-1", time.time())
        result = store.invalidate("task-a", "rework_requested")

        assert result is not None
        assert not result.valid
        assert result.reason == "rework_requested"
        assert result.invalidated_at > 0

        checked = store.check("task-a")
        assert not checked.valid

    def test_invalidate_already_invalid(self, temp_storage):
        store = temp_storage.tokens
        store.create("task-a", "agent-1", time.time())
        store.invalidate("task-a", "first")
        result = store.invalidate("task-a", "second")
        assert result.reason == "first"

    def test_cleanup(self, temp_storage):
        store = temp_storage.tokens
        store.create("task-a", "agent-1", time.time())
        store.cleanup("task-a")
        assert store.check("task-a") is None

    def test_cleanup_nonexistent(self, temp_storage):
        temp_storage.tokens.cleanup("nonexistent")


class TestCancelNotifier:
    """Tests for push cancellation via notifiers."""

    def test_file_notifier(self, temp_storage):
        notify_path = temp_storage.base_dir / "test-cancel.json"
        store = temp_storage.tokens
        store.create("task-a", "agent-1", time.time(),
                     notifier=FileNotifier(notify_path))
        store.invalidate("task-a", "cancelled")
        assert notify_path.exists()

    def test_callback_notifier(self, temp_storage):
        received = []
        store = temp_storage.tokens
        store.create("task-a", "agent-1", time.time(),
                     notifier=CallbackNotifier(lambda t: received.append(t)))
        store.invalidate("task-a", "timed_out")
        assert len(received) == 1
        assert received[0].reason == "timed_out"

    def test_cancellation_token_as_notifier(self, temp_storage):
        ct = CancellationToken()
        assert isinstance(ct, CancelNotifier)

        store = temp_storage.tokens
        store.create("task-a", "agent-1", time.time(), notifier=ct)
        assert not ct.is_cancelled

        store.invalidate("task-a", "released")
        assert ct.is_cancelled
        assert ct.reason == "released"

    def test_cancellation_token_callback_chain(self, temp_storage):
        ct = CancellationToken()
        called = []
        ct.register_callback(lambda: called.append(True))

        store = temp_storage.tokens
        store.create("task-a", "agent-1", time.time(), notifier=ct)
        store.invalidate("task-a", "rework")
        assert called == [True]


class TestTokenIntegration:
    """Tests for token integration with tools."""

    def test_get_task_creates_token(self, temp_storage):
        add_node.add_node(temp_storage, {"node_id": "a"})
        get_task.get_task(temp_storage, {"agent_id": "w1", "task_id": "a"})

        token = temp_storage.tokens.check("a")
        assert token is not None
        assert token.valid
        assert token.agent_id == "w1"

    def test_finish_complete_cleans_token(self, temp_storage):
        add_node.add_node(temp_storage, {"node_id": "a"})
        get_task.get_task(temp_storage, {"agent_id": "w1", "task_id": "a"})
        finish_task.finish_task(temp_storage, {"task_id": "a", "success": True, "summary": "done"})

        assert temp_storage.tokens.check("a") is None

    def test_finish_release_invalidates_token(self, temp_storage):
        add_node.add_node(temp_storage, {"node_id": "a"})
        get_task.get_task(temp_storage, {"agent_id": "w1", "task_id": "a"})
        finish_task.finish_task(temp_storage, {"task_id": "a", "release": True})

        token = temp_storage.tokens.check("a")
        assert not token.valid
        assert token.reason == "released"

    def test_check_task_tool(self, temp_storage):
        add_node.add_node(temp_storage, {"node_id": "a"})
        get_task.get_task(temp_storage, {"agent_id": "w1", "task_id": "a"})

        r = check_task.check_task(temp_storage, {"task_id": "a"})
        assert r["success"]
        assert r["data"]["valid"]

    def test_check_task_no_token(self, temp_storage):
        r = check_task.check_task(temp_storage, {"task_id": "nope"})
        assert r["data"]["valid"] is False


class TestActiveProtection:
    """Tests for ACTIVE node protection on remove/split."""

    def test_cannot_remove_active_node(self, temp_storage):
        add_node.add_node(temp_storage, {"node_id": "a"})
        get_task.get_task(temp_storage, {"agent_id": "w1", "task_id": "a"})

        r = remove_node.remove_node(temp_storage, {"node_id": "a"})
        assert not r["success"]
        assert "ACTIVE" in r["message"]
        assert "release" in r["message"].lower()

    def test_cannot_split_active_node(self, temp_storage):
        add_node.add_node(temp_storage, {"node_id": "a"})
        get_task.get_task(temp_storage, {"agent_id": "w1", "task_id": "a"})

        r = split_node.split_node(temp_storage, {
            "parent_id": "a",
            "new_nodes": [{"node_id": "a1"}, {"node_id": "a2"}],
        })
        assert not r["success"]
        assert "ACTIVE" in r["message"]

    def test_can_remove_after_release(self, temp_storage):
        add_node.add_node(temp_storage, {"node_id": "a"})
        get_task.get_task(temp_storage, {"agent_id": "w1", "task_id": "a"})
        finish_task.finish_task(temp_storage, {"task_id": "a", "release": True})

        r = remove_node.remove_node(temp_storage, {"node_id": "a"})
        assert r["success"]

    def test_can_split_after_release(self, temp_storage):
        add_node.add_node(temp_storage, {"node_id": "a"})
        get_task.get_task(temp_storage, {"agent_id": "w1", "task_id": "a"})
        finish_task.finish_task(temp_storage, {"task_id": "a", "release": True})

        r = split_node.split_node(temp_storage, {
            "parent_id": "a",
            "new_nodes": [{"node_id": "a1"}, {"node_id": "a2"}],
        })
        assert r["success"]
