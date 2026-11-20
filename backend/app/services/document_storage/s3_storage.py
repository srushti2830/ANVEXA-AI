"""S3-compatible object storage backend for production document uploads."""

from __future__ import annotations

from typing import Any

from app.services.document_storage.storage_service import (
    StorageBackend,
    StorageError,
)


class S3StorageBackend(StorageBackend):
    def __init__(
        self,
        *,
        bucket: str,
        region: str | None = None,
        endpoint_url: str | None = None,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        prefix: str = "anvexa/documents",
    ) -> None:
        try:
            import boto3
        except ImportError as exc:
            raise StorageError("boto3 is required for S3 object storage") from exc

        client_kwargs: dict[str, Any] = {}
        if region:
            client_kwargs["region_name"] = region
        if endpoint_url:
            client_kwargs["endpoint_url"] = endpoint_url
        if access_key_id and secret_access_key:
            client_kwargs["aws_access_key_id"] = access_key_id
            client_kwargs["aws_secret_access_key"] = secret_access_key

        self._bucket = bucket
        self._prefix = prefix.strip("/")
        self._client = boto3.client("s3", **client_kwargs)

    def _key(self, storage_key: str) -> str:
        clean = storage_key.replace("\\", "/").lstrip("/")
        if not clean or ".." in clean.split("/"):
            raise StorageError("Invalid storage key")
        return f"{self._prefix}/{clean}" if self._prefix else clean

    def save(self, storage_key: str, data: bytes) -> str:
        key = self._key(storage_key)
        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ServerSideEncryption="AES256",
            )
            return f"s3://{self._bucket}/{key}"
        except Exception as exc:
            raise StorageError("Failed to save file to object storage") from exc

    def delete(self, storage_key: str) -> None:
        key = self._key(storage_key)
        try:
            self._client.delete_object(Bucket=self._bucket, Key=key)
        except Exception as exc:
            raise StorageError("Failed to delete file from object storage") from exc

    def exists(self, storage_key: str) -> bool:
        key = self._key(storage_key)
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except Exception:
            return False

    def read(self, storage_key: str) -> bytes:
        key = self._key(storage_key)
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
            return response["Body"].read()
        except Exception as exc:
            raise StorageError("Failed to read file from object storage") from exc

    def get_path(self, storage_key: str) -> str:
        return f"s3://{self._bucket}/{self._key(storage_key)}"
