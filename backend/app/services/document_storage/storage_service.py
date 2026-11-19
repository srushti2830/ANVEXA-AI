"""Abstract storage backend protocol for document file storage."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class StorageBackend(ABC):
    """Interface for document storage backends.

    Implementations handle the physical persistence of uploaded document files.
    The interface is intentionally minimal to allow swapping local filesystem
    storage for cloud object storage (GCS, S3, etc.) without changing callers.
    """

    @abstractmethod
    def save(self, storage_key: str, data: bytes) -> str:
        """Persist *data* under *storage_key* and return the canonical path/URI.

        Raises ``StorageError`` on failure.
        """

    @abstractmethod
    def delete(self, storage_key: str) -> None:
        """Remove the object identified by *storage_key*.

        Must be idempotent — deleting a non-existent key is a no-op.
        """

    @abstractmethod
    def exists(self, storage_key: str) -> bool:
        """Return ``True`` if an object with *storage_key* exists."""

    @abstractmethod
    def get_path(self, storage_key: str) -> str:
        """Return the canonical internal path/URI for *storage_key*.

        The return value is intended for internal bookkeeping only and
        **must not** be exposed to API consumers.
        """


class StorageError(Exception):
    """Raised when a storage operation fails."""
