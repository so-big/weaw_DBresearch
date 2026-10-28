"""Where encrypted file versions live. Ciphertext only (CLAUDE.md).

`LocalBlobStore` keeps files in a folder (the `blobs` Docker volume), sharded by key prefix.
An S3 implementation can replace it later without touching callers (MinIO is discontinued).
"""

import os
import uuid
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from typing import BinaryIO, Protocol

from dbresearch.config import get_settings


class BlobStore(Protocol):
    def new_key(self) -> str: ...
    def writer(self, key: str) -> AbstractContextManager[BinaryIO]: ...
    def open(self, key: str) -> BinaryIO: ...
    def delete(self, key: str) -> None: ...
    def exists(self, key: str) -> bool: ...


class LocalBlobStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, key: str) -> Path:
        if not key.isalnum():
            raise ValueError("invalid blob key")
        return self.root / key[:2] / key[2:4] / key

    def new_key(self) -> str:
        return uuid.uuid4().hex

    @contextmanager
    def writer(self, key: str) -> Iterator[BinaryIO]:
        """Write atomically: a crash or error never leaves a partial blob under `key`."""
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".partial")
        try:
            with open(tmp, "xb") as handle:
                yield handle
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, path)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise

    def open(self, key: str) -> BinaryIO:
        return open(self._path(key), "rb")

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()


def get_blobstore() -> LocalBlobStore:
    return LocalBlobStore(get_settings().blob_dir)
