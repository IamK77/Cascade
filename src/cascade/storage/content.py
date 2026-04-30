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

"""Content-addressable blob storage.

Artifacts are stored by hash and retrieved by hash. The hash algorithm
is an implementation detail — the protocol only guarantees that put()
returns an opaque ref that get() can resolve.

Two built-in implementations:
    - LocalContentStore: SHA-256, filesystem blobs in .cascade/blobs/
    - GitContentStore: Git-native hash, uses git object database
"""

import hashlib
import subprocess
from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class ContentStore(Protocol):
    """Content-addressable storage protocol.

    ref is an opaque string — callers must not assume any particular
    hash algorithm. The only guarantee: put(content) returns a ref
    that get(ref) can resolve back to the original content.
    """

    def put(self, content: str) -> str: ...

    def get(self, ref: str) -> str | None: ...

    def exists(self, ref: str) -> bool: ...


class LocalContentStore:
    """SHA-256 content store backed by local filesystem.

    Storage layout: base_dir/blobs/{sha256_hex}
    """

    def __init__(self, base_dir: Path | str):
        self._dir = Path(base_dir) / "blobs"

    def put(self, content: str) -> str:
        ref = hashlib.sha256(content.encode("utf-8")).hexdigest()
        path = self._dir / ref
        if not path.exists():
            self._dir.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        return ref

    def get(self, ref: str) -> str | None:
        path = self._dir / ref
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def exists(self, ref: str) -> bool:
        return (self._dir / ref).exists()


class GitContentStore:
    """Content store backed by Git's object database.

    Uses git hash-object / git cat-file. The ref is Git's native
    object hash (SHA-1 or SHA-256 depending on the repo's
    extensions.objectFormat).
    """

    def __init__(self, repo_dir: Path | str | None = None):
        if repo_dir is not None:
            self._repo = Path(repo_dir)
            r = self._git("rev-parse", "--git-dir")
            if r.returncode != 0:
                raise RuntimeError(f"Not in a git repository: {self._repo}")
        else:
            self._repo = self._discover_repo()

    @staticmethod
    def _discover_repo() -> Path:
        r = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            raise RuntimeError("Not in a git repository")
        return Path(r.stdout.strip())

    def _git(self, *args: str, input: str | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=self._repo,
            input=input,
            capture_output=True,
            text=True,
        )

    def put(self, content: str) -> str:
        r = self._git("hash-object", "-w", "--stdin", input=content)
        if r.returncode != 0:
            raise RuntimeError(f"git hash-object failed: {r.stderr.strip()}")
        return r.stdout.strip()

    def get(self, ref: str) -> str | None:
        r = self._git("cat-file", "blob", ref)
        if r.returncode != 0:
            return None
        return r.stdout

    def exists(self, ref: str) -> bool:
        r = self._git("cat-file", "-e", ref)
        return r.returncode == 0
