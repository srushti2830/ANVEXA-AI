from __future__ import annotations

import pytest
import sys
import types
from pydantic import ValidationError

from app.core.config import Settings


def test_production_rejects_local_object_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANVEXA_DATABASE_URL", raising=False)
    with pytest.raises(ValidationError, match="object storage"):
        Settings(
            _env_file=None,
            environment="production",
            database_url="postgresql+psycopg://user:pass@localhost/db",
            jwt_secret_key="a-private-production-secret-with-32-characters",
            dev_database_mode=False,
            object_storage_backend="local",
        )


def test_production_accepts_s3_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANVEXA_DATABASE_URL", raising=False)
    settings = Settings(
        _env_file=None,
        environment="production",
        database_url="postgresql+psycopg://user:pass@localhost/db",
        jwt_secret_key="a-private-production-secret-with-32-characters",
        dev_database_mode=False,
        object_storage_backend="s3",
        s3_bucket="anvexa-production",
        s3_access_key_id="test-access-key",
        s3_secret_access_key="test-secret-key",
    )
    assert settings.object_storage_backend == "s3"


def test_s3_backend_saves_and_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    stored: dict[str, bytes] = {}

    class FakeBody:
        def __init__(self, data: bytes) -> None:
            self.data = data

        def read(self) -> bytes:
            return self.data

    class FakeS3:
        def put_object(self, **kwargs) -> None:
            stored[kwargs["Key"]] = kwargs["Body"]

        def delete_object(self, **kwargs) -> None:
            stored.pop(kwargs["Key"], None)

        def head_object(self, **kwargs) -> None:
            if kwargs["Key"] not in stored:
                raise RuntimeError("missing")

        def get_object(self, **kwargs) -> dict[str, object]:
            return {"Body": FakeBody(stored[kwargs["Key"]])}

    fake_boto3 = types.ModuleType("boto3")
    fake_boto3.client = lambda *args, **kwargs: FakeS3()
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)

    from app.services.document_storage.s3_storage import S3StorageBackend

    backend = S3StorageBackend(
        bucket="test-bucket",
        access_key_id="access",
        secret_access_key="secret",
    )
    backend.save("abc123.pdf", b"%PDF-test")
    assert backend.read("abc123.pdf") == b"%PDF-test"
    assert backend.exists("abc123.pdf")
