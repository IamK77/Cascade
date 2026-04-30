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

"""Tests for ContentStore protocol and implementations."""

import hashlib
import shutil
import subprocess
from pathlib import Path

import pytest

from cascade.storage.content import ContentStore, GitContentStore, LocalContentStore


class TestLocalContentStore:
    @pytest.fixture
    def store(self, tmp_path: Path) -> LocalContentStore:
        return LocalContentStore(tmp_path)

    def test_put_returns_sha256(self, store: LocalContentStore):
        content = "hello world"
        ref = store.put(content)
        expected = hashlib.sha256(content.encode("utf-8")).hexdigest()
        assert ref == expected
        assert len(ref) == 64

    def test_get_round_trip(self, store: LocalContentStore):
        content = "test content with unicode: 你好世界"
        ref = store.put(content)
        assert store.get(ref) == content

    def test_get_missing(self, store: LocalContentStore):
        assert store.get("nonexistent") is None

    def test_exists(self, store: LocalContentStore):
        assert not store.exists("nonexistent")
        ref = store.put("data")
        assert store.exists(ref)

    def test_put_idempotent(self, store: LocalContentStore, tmp_path: Path):
        content = "same content"
        ref1 = store.put(content)
        ref2 = store.put(content)
        assert ref1 == ref2
        blobs = list((tmp_path / "blobs").iterdir())
        assert len(blobs) == 1

    def test_different_content_different_ref(self, store: LocalContentStore):
        ref1 = store.put("content A")
        ref2 = store.put("content B")
        assert ref1 != ref2

    def test_blobs_dir_created_on_first_put(self, tmp_path: Path):
        store = LocalContentStore(tmp_path)
        assert not (tmp_path / "blobs").exists()
        store.put("trigger creation")
        assert (tmp_path / "blobs").is_dir()

    def test_satisfies_protocol(self, store: LocalContentStore):
        assert isinstance(store, ContentStore)


@pytest.mark.skipif(shutil.which("git") is None, reason="git not available")
class TestGitContentStore:
    @pytest.fixture
    def git_repo(self, tmp_path: Path) -> Path:
        subprocess.run(
            ["git", "init"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        return tmp_path

    @pytest.fixture
    def store(self, git_repo: Path) -> GitContentStore:
        return GitContentStore(git_repo)

    def test_put_and_get_round_trip(self, store: GitContentStore):
        content = "hello from git"
        ref = store.put(content)
        assert store.get(ref) == content

    def test_get_missing(self, store: GitContentStore):
        assert store.get("0" * 40) is None

    def test_exists(self, store: GitContentStore):
        assert not store.exists("0" * 40)
        ref = store.put("data")
        assert store.exists(ref)

    def test_put_idempotent(self, store: GitContentStore):
        ref1 = store.put("same content")
        ref2 = store.put("same content")
        assert ref1 == ref2

    def test_unicode_content(self, store: GitContentStore):
        content = "多语言支持: 日本語 한국어 العربية"
        ref = store.put(content)
        assert store.get(ref) == content

    def test_not_a_git_repo(self, tmp_path: Path):
        non_repo = tmp_path / "not_a_repo"
        non_repo.mkdir()
        with pytest.raises(RuntimeError, match="Not in a git repository"):
            GitContentStore(non_repo)

    def test_satisfies_protocol(self, store: GitContentStore):
        assert isinstance(store, ContentStore)


class TestFileStorageWithContentStore:
    """Test that FileStorage correctly delegates to ContentStore."""

    def test_custom_content_store(self, tmp_path: Path):
        from cascade.core.cascade import Cascade
        from cascade.core.node import Node
        from cascade.core.state import NodeState
        from cascade.storage.file_storage import FileStorage
        from cascade.types import Context

        content_store = LocalContentStore(tmp_path / "custom_blobs")
        storage = FileStorage(tmp_path / ".cascade", content=content_store)

        cascade = Cascade()
        node = Node(
            id="task",
            state=NodeState.READY,
            context=Context(artifacts="custom store content"),
        )
        cascade.add_node(node)

        with storage.lock():
            storage.save(cascade)

        ref = content_store.put("custom store content")
        assert content_store.get(ref) == "custom store content"

        loaded = storage.load()
        assert loaded.nodes["task"].context.artifacts == "custom store content"
