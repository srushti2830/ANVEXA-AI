"""Local filesystem storage backend for document files."""

from __future__ import annotations

import logging
from pathlib import Path

from app.services.document_storage.storage_service import (
    StorageBackend,
    StorageError,
)

logger = logging.getLogger(__name__)


class LocalStorageBackend(StorageBackend):
    """Stores files on the local filesystem under a configurable root directory.

    Directory structure::

        <root>/
            <first-2-chars-of-key>/
                <storage_key>
    """

    def __init__(self, root_dir: str | Path) -> None:
        self._root = Path(root_dir).resolve()
        self._root.mkdir(parents=True, exist_ok=True)
        logger.info("LocalStorageBackend initialized at %s", self._root)

    # -- internal helpers --------------------------------------------------

    def _resolve(self, storage_key: str) -> Path:
        """Return a safe resolved path for *storage_key*, preventing traversal."""
        # Sanitize: strip leading slashes and disallow traversal characters
        clean = storage_key.replace("\\", "/").lstrip("/")
        if ".." in clean.split("/"):
            raise StorageError("Path traversal detected in storage key")

        # Sub-directory bucketing by first 2 chars of key (reduces inode pressure)
        bucket = clean[:2] if len(clean) >= 2 else "00"
        target = (self._root / bucket / clean).resolve()

        # Final safety: ensure the resolved path is under our root
        if not str(target).startswith(str(self._root)):
            raise StorageError("Path traversal detected in storage key")
        return target

    # -- public interface --------------------------------------------------

    def save(self, storage_key: str, data: bytes) -> str:
        """Write *data* to disk under *storage_key*."""
        try:
            target = self._resolve(storage_key)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            logger.info("Saved %d bytes to %s", len(data), target)
            return str(target)
        except StorageError:
            raise
        except Exception as exc:
            logger.exception("Failed to save storage_key=%s", storage_key)
            raise StorageError(f"Failed to save file: {exc}") from exc

    def delete(self, storage_key: str) -> None:
        """Delete file from disk.  Idempotent — missing files are silently ignored."""
        try:
            target = self._resolve(storage_key)
            if target.is_file():
                target.unlink()
                logger.info("Deleted %s", target)
        except StorageError:
            raise
        except Exception as exc:
            logger.exception("Failed to delete storage_key=%s", storage_key)
            raise StorageError(f"Failed to delete file: {exc}") from exc

    def exists(self, storage_key: str) -> bool:
        try:
            return self._resolve(storage_key).is_file()
        except StorageError:
            return False

    def read(self, storage_key: str) -> bytes:
        """Read and return the raw bytes for *storage_key*."""
        try:
            target = self._resolve(storage_key)
            if not target.is_file():
                raise StorageError(f"File not found: {storage_key}")
            return target.read_bytes()
        except StorageError:
            raise
        except Exception as exc:
            logger.exception("Failed to read storage_key=%s", storage_key)
            raise StorageError(f"Failed to read file: {exc}") from exc

    def get_path(self, storage_key: str) -> str:
        return str(self._resolve(storage_key))
