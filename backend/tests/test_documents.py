"""Comprehensive tests for Phase 4 — Document Management System."""

from __future__ import annotations

import asyncio
import io
import os
import tempfile
import zipfile
from typing import Iterator
from unittest.mock import patch
import uuid

import httpx
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password, rate_limiter
from app.database.base import Base
from app.database.session import get_db
from app.main import create_app
from app.models.document import Document
from app.models.enums import DocumentStatus, UserRole
from app.models.user import User
from app.services.document_service import (
    reset_storage_backend,
    set_storage_backend,
)
from app.services.document_storage.local_storage import LocalStorageBackend
from app.services.document_storage.storage_service import (
    StorageBackend,
    StorageError,
)


# ---------------------------------------------------------------------------
# Minimal valid file fixtures
# ---------------------------------------------------------------------------


def make_pdf_bytes(size: int = 256) -> bytes:
    """Return minimal valid PDF content."""
    # Minimal PDF 1.4 structure
    content = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\n"
        b"xref\n0 4\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"trailer<</Size 4/Root 1 0 R>>\n"
        b"startxref\n183\n%%EOF\n"
    )
    if len(content) < size:
        content += b"\x00" * (size - len(content))
    return content


def make_docx_bytes() -> bytes:
    """Return minimal valid DOCX (ZIP with [Content_Types].xml)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/'
            'package/2006/content-types">'
            '<Default Extension="rels" ContentType='
            '"application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            "</Types>",
        )
        zf.writestr(
            "word/document.xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/'
            'wordprocessingml/2006/main">'
            "<w:body><w:p><w:r><w:t>Test</w:t></w:r></w:p></w:body>"
            "</w:document>",
        )
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def setup_test_settings(monkeypatch):
    """Ensure consistent JWT secret and clean settings cache for all tests."""
    monkeypatch.setenv(
        "ANVEXA_JWT_SECRET_KEY",
        "test-secret-key-for-testing-purposes-only-32bytes!",
    )
    get_settings.cache_clear()
    rate_limiter.reset_all()
    reset_storage_backend()
    yield
    get_settings.cache_clear()
    rate_limiter.reset_all()
    reset_storage_backend()


@pytest.fixture
def tmp_storage_dir():
    """Create a temporary directory for file storage during tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def doc_db_session() -> Iterator[Session]:
    """Provide an isolated in-memory SQLite database for document testing."""
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    tables = [
        table
        for table in Base.metadata.sorted_tables
        if table.name != "embeddings"
    ]
    Base.metadata.create_all(engine, tables=tables)

    with Session(engine) as session:
        yield session

    engine.dispose()


def multipart_request(
    app,
    method: str,
    path: str,
    files: dict | None = None,
    headers: dict | None = None,
    params: dict | None = None,
) -> httpx.Response:
    """Synchronous helper for multipart and regular requests."""

    async def run_req() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.request(
                method, path, files=files, headers=headers, params=params
            )

    return asyncio.run(run_req())


def json_request(
    app,
    method: str,
    path: str,
    json: dict | None = None,
    headers: dict | None = None,
    params: dict | None = None,
) -> httpx.Response:
    """Synchronous helper for JSON requests."""

    async def run_req() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.request(
                method, path, json=json, headers=headers, params=params
            )

    return asyncio.run(run_req())


@pytest.fixture
def doc_test_client(doc_db_session: Session, tmp_storage_dir: str, monkeypatch):
    """Create a FastAPI test client with document storage configured."""
    monkeypatch.setenv("ANVEXA_DOCUMENT_STORAGE_PATH", tmp_storage_dir)
    get_settings.cache_clear()
    reset_storage_backend()

    application = create_app()

    def override_get_db():
        yield doc_db_session

    application.dependency_overrides[get_db] = override_get_db

    class DocClientWrapper:
        def upload(self, path: str, file_bytes: bytes, filename: str, headers=None):
            return multipart_request(
                application,
                "POST",
                path,
                files={"file": (filename, file_bytes)},
                headers=headers,
            )

        def get(self, path: str, headers=None, params=None):
            return json_request(
                application, "GET", path, headers=headers, params=params
            )

        def delete(self, path: str, headers=None):
            return json_request(application, "DELETE", path, headers=headers)

        def post(self, path: str, json=None, headers=None):
            return json_request(application, "POST", path, json=json, headers=headers)

    return DocClientWrapper()


@pytest.fixture
def test_user(doc_db_session: Session) -> User:
    """Create a test user and return it."""
    user = User(
        email="docuser@test.org",
        full_name="Doc Test User",
        hashed_password=hash_password("Password123!"),
        role=UserRole.USER,
        is_active=True,
    )
    doc_db_session.add(user)
    doc_db_session.commit()
    doc_db_session.refresh(user)
    return user


@pytest.fixture
def test_user_token(test_user: User) -> str:
    return create_access_token(
        user_id=test_user.id,
        email=test_user.email,
        role=test_user.role.value,
    )


@pytest.fixture
def auth_headers(test_user_token: str) -> dict:
    return {"Authorization": f"Bearer {test_user_token}"}


@pytest.fixture
def second_user(doc_db_session: Session) -> User:
    """Create a second test user for IDOR tests."""
    user = User(
        email="otheruser@test.org",
        full_name="Other User",
        hashed_password=hash_password("Password123!"),
        role=UserRole.USER,
        is_active=True,
    )
    doc_db_session.add(user)
    doc_db_session.commit()
    doc_db_session.refresh(user)
    return user


@pytest.fixture
def second_user_headers(second_user: User) -> dict:
    token = create_access_token(
        user_id=second_user.id,
        email=second_user.email,
        role=second_user.role.value,
    )
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Upload Tests
# ---------------------------------------------------------------------------


def test_valid_pdf_upload(doc_test_client, auth_headers) -> None:
    """Uploading a valid PDF file succeeds."""
    response = doc_test_client.upload(
        "/api/v1/documents/upload",
        make_pdf_bytes(),
        "research_paper.pdf",
        headers=auth_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["filename"] == "research_paper.pdf"
    assert "pdf" in data["file_type"].lower()
    assert data["file_size"] > 0
    assert len(data["file_hash"]) == 64
    assert data["processing_status"] == "uploaded"
    assert data["message"] == "Document uploaded successfully"


def test_valid_docx_upload(doc_test_client, auth_headers) -> None:
    """Uploading a valid DOCX file succeeds."""
    response = doc_test_client.upload(
        "/api/v1/documents/upload",
        make_docx_bytes(),
        "thesis.docx",
        headers=auth_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["filename"] == "thesis.docx"
    assert data["file_size"] > 0


def test_unsupported_extension(doc_test_client, auth_headers) -> None:
    """Files with unsupported extensions are rejected with 422."""
    for ext in [".txt", ".exe", ".jpg", ".html"]:
        response = doc_test_client.upload(
            "/api/v1/documents/upload",
            b"some content here",
            f"file{ext}",
            headers=auth_headers,
        )
        assert response.status_code == 422
        assert "Unsupported file type" in response.json()["detail"]


def test_invalid_file_content(doc_test_client, auth_headers) -> None:
    """Files whose content doesn't match the declared extension are rejected."""
    # Claim it's a PDF but send garbage
    response = doc_test_client.upload(
        "/api/v1/documents/upload",
        b"This is definitely not a PDF file content",
        "fake.pdf",
        headers=auth_headers,
    )
    assert response.status_code == 422
    assert "does not match PDF format" in response.json()["detail"]

    # Claim it's a DOCX but send garbage (not a ZIP)
    response = doc_test_client.upload(
        "/api/v1/documents/upload",
        b"This is definitely not a DOCX file content",
        "fake.docx",
        headers=auth_headers,
    )
    assert response.status_code == 422
    assert "does not match DOCX format" in response.json()["detail"]


def test_empty_upload(doc_test_client, auth_headers) -> None:
    """Empty file uploads are rejected."""
    response = doc_test_client.upload(
        "/api/v1/documents/upload",
        b"",
        "empty.pdf",
        headers=auth_headers,
    )
    assert response.status_code == 422
    assert "empty" in response.json()["detail"].lower()


def test_oversized_file(doc_test_client, auth_headers, monkeypatch) -> None:
    """Files exceeding max upload size are rejected."""
    # Set a very small limit
    monkeypatch.setenv("ANVEXA_MAX_UPLOAD_SIZE_BYTES", "100")
    get_settings.cache_clear()

    response = doc_test_client.upload(
        "/api/v1/documents/upload",
        make_pdf_bytes(500),
        "large.pdf",
        headers=auth_headers,
    )
    assert response.status_code == 413
    assert "exceeds maximum" in response.json()["detail"]


def test_duplicate_file(doc_test_client, auth_headers) -> None:
    """Uploading the same file twice (same user, same content hash) is rejected."""
    pdf_data = make_pdf_bytes()

    # First upload succeeds
    res1 = doc_test_client.upload(
        "/api/v1/documents/upload",
        pdf_data,
        "first_copy.pdf",
        headers=auth_headers,
    )
    assert res1.status_code == 201

    # Second upload with same content is rejected
    res2 = doc_test_client.upload(
        "/api/v1/documents/upload",
        pdf_data,
        "second_copy.pdf",
        headers=auth_headers,
    )
    assert res2.status_code == 409
    assert "Duplicate" in res2.json()["detail"]


# ---------------------------------------------------------------------------
# Document Listing and Pagination
# ---------------------------------------------------------------------------


def _upload_multiple(client, auth_headers, count: int = 5):
    """Helper to upload multiple distinct PDF files."""
    for i in range(count):
        # Each PDF must have unique content for unique hash
        content = make_pdf_bytes() + f"unique-{i}".encode()
        client.upload(
            "/api/v1/documents/upload",
            content,
            f"paper_{i}.pdf",
            headers=auth_headers,
        )


def test_document_listing(doc_test_client, auth_headers) -> None:
    """Documents can be listed with pagination metadata."""
    _upload_multiple(doc_test_client, auth_headers, 3)

    response = doc_test_client.get(
        "/api/v1/documents",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["documents"]) == 3
    assert data["pagination"]["total"] == 3
    assert data["pagination"]["page"] == 1


def test_pagination(doc_test_client, auth_headers) -> None:
    """Pagination parameters work correctly."""
    _upload_multiple(doc_test_client, auth_headers, 5)

    # Request page 1 with 2 per page
    res = doc_test_client.get(
        "/api/v1/documents",
        headers=auth_headers,
        params={"page": "1", "per_page": "2"},
    )
    assert res.status_code == 200
    data = res.json()
    assert len(data["documents"]) == 2
    assert data["pagination"]["total"] == 5
    assert data["pagination"]["total_pages"] == 3

    # Request page 3 — should have 1 document
    res2 = doc_test_client.get(
        "/api/v1/documents",
        headers=auth_headers,
        params={"page": "3", "per_page": "2"},
    )
    assert res2.status_code == 200
    assert len(res2.json()["documents"]) == 1


def test_document_search(doc_test_client, auth_headers) -> None:
    """Documents can be searched by filename."""
    doc_test_client.upload(
        "/api/v1/documents/upload",
        make_pdf_bytes() + b"a",
        "quantum_mechanics.pdf",
        headers=auth_headers,
    )
    doc_test_client.upload(
        "/api/v1/documents/upload",
        make_pdf_bytes() + b"b",
        "classical_physics.pdf",
        headers=auth_headers,
    )

    # Search for "quantum"
    res = doc_test_client.get(
        "/api/v1/documents",
        headers=auth_headers,
        params={"search": "quantum"},
    )
    assert res.status_code == 200
    docs = res.json()["documents"]
    assert len(docs) == 1
    assert "quantum" in docs[0]["filename"].lower()


def test_filter_by_status(doc_test_client, auth_headers) -> None:
    """Documents can be filtered by processing status."""
    doc_test_client.upload(
        "/api/v1/documents/upload",
        make_pdf_bytes(),
        "status_test.pdf",
        headers=auth_headers,
    )

    # Filter by UPLOADED — should find the document
    res = doc_test_client.get(
        "/api/v1/documents",
        headers=auth_headers,
        params={"status": "uploaded"},
    )
    assert res.status_code == 200
    assert len(res.json()["documents"]) == 1

    # Filter by COMPLETED — should find nothing
    res2 = doc_test_client.get(
        "/api/v1/documents",
        headers=auth_headers,
        params={"status": "completed"},
    )
    assert res2.status_code == 200
    assert len(res2.json()["documents"]) == 0


# ---------------------------------------------------------------------------
# Document Retrieval
# ---------------------------------------------------------------------------


def test_document_retrieval(doc_test_client, auth_headers) -> None:
    """A single document can be retrieved by ID."""
    upload_res = doc_test_client.upload(
        "/api/v1/documents/upload",
        make_pdf_bytes(),
        "retrieve_me.pdf",
        headers=auth_headers,
    )
    doc_id = upload_res.json()["id"]

    res = doc_test_client.get(
        f"/api/v1/documents/{doc_id}",
        headers=auth_headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == doc_id
    assert data["filename"] == "retrieve_me.pdf"
    # Ensure storage_path is NOT exposed
    assert "storage_path" not in data


def test_document_status_endpoint(doc_test_client, auth_headers) -> None:
    """The status endpoint returns lightweight status info."""
    upload_res = doc_test_client.upload(
        "/api/v1/documents/upload",
        make_pdf_bytes(),
        "status_check.pdf",
        headers=auth_headers,
    )
    doc_id = upload_res.json()["id"]

    res = doc_test_client.get(
        f"/api/v1/documents/{doc_id}/status",
        headers=auth_headers,
    )
    assert res.status_code == 200
    assert res.json()["processing_status"] == "uploaded"


def test_missing_document(doc_test_client, auth_headers) -> None:
    """Requesting a non-existent document returns 404."""
    fake_id = uuid.uuid4()
    res = doc_test_client.get(
        f"/api/v1/documents/{fake_id}",
        headers=auth_headers,
    )
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Authorization and Security
# ---------------------------------------------------------------------------


def test_unauthorized_upload(doc_test_client) -> None:
    """Upload without authentication token is rejected."""
    response = doc_test_client.upload(
        "/api/v1/documents/upload",
        make_pdf_bytes(),
        "unauthorized.pdf",
    )
    assert response.status_code == 401


def test_unauthorized_listing(doc_test_client) -> None:
    """Listing documents without authentication is rejected."""
    response = doc_test_client.get("/api/v1/documents")
    assert response.status_code == 401


def test_cross_user_document_access(
    doc_test_client, auth_headers, second_user_headers
) -> None:
    """Users cannot access documents uploaded by another user (IDOR protection)."""
    # User 1 uploads a document
    upload_res = doc_test_client.upload(
        "/api/v1/documents/upload",
        make_pdf_bytes(),
        "private.pdf",
        headers=auth_headers,
    )
    doc_id = upload_res.json()["id"]

    # User 2 tries to access User 1's document
    res = doc_test_client.get(
        f"/api/v1/documents/{doc_id}",
        headers=second_user_headers,
    )
    assert res.status_code == 403

    # User 2 tries to delete User 1's document
    del_res = doc_test_client.delete(
        f"/api/v1/documents/{doc_id}",
        headers=second_user_headers,
    )
    assert del_res.status_code == 403

    # User 2 tries to get status of User 1's document
    status_res = doc_test_client.get(
        f"/api/v1/documents/{doc_id}/status",
        headers=second_user_headers,
    )
    assert status_res.status_code == 403


def test_cross_user_listing_isolation(
    doc_test_client, auth_headers, second_user_headers
) -> None:
    """Users only see their own documents in listing."""
    # User 1 uploads
    doc_test_client.upload(
        "/api/v1/documents/upload",
        make_pdf_bytes(),
        "user1_doc.pdf",
        headers=auth_headers,
    )

    # User 2 uploads different content
    doc_test_client.upload(
        "/api/v1/documents/upload",
        make_pdf_bytes() + b"different",
        "user2_doc.pdf",
        headers=second_user_headers,
    )

    # User 1 sees only their document
    res1 = doc_test_client.get("/api/v1/documents", headers=auth_headers)
    assert res1.status_code == 200
    docs1 = res1.json()["documents"]
    assert len(docs1) == 1
    assert docs1[0]["filename"] == "user1_doc.pdf"

    # User 2 sees only their document
    res2 = doc_test_client.get("/api/v1/documents", headers=second_user_headers)
    assert res2.status_code == 200
    docs2 = res2.json()["documents"]
    assert len(docs2) == 1
    assert docs2[0]["filename"] == "user2_doc.pdf"


# ---------------------------------------------------------------------------
# Document Deletion
# ---------------------------------------------------------------------------


def test_document_deletion(doc_test_client, auth_headers) -> None:
    """Documents can be deleted by their owner."""
    upload_res = doc_test_client.upload(
        "/api/v1/documents/upload",
        make_pdf_bytes(),
        "deletable.pdf",
        headers=auth_headers,
    )
    doc_id = upload_res.json()["id"]

    # Delete
    del_res = doc_test_client.delete(
        f"/api/v1/documents/{doc_id}",
        headers=auth_headers,
    )
    assert del_res.status_code == 200
    assert "deleted" in del_res.json()["message"].lower()

    # Verify it's gone
    get_res = doc_test_client.get(
        f"/api/v1/documents/{doc_id}",
        headers=auth_headers,
    )
    assert get_res.status_code == 404


def test_delete_nonexistent_document(doc_test_client, auth_headers) -> None:
    """Deleting a non-existent document returns 404."""
    fake_id = uuid.uuid4()
    res = doc_test_client.delete(
        f"/api/v1/documents/{fake_id}",
        headers=auth_headers,
    )
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# Storage Failure Simulation
# ---------------------------------------------------------------------------


def test_storage_failure(doc_test_client, auth_headers) -> None:
    """Storage errors during upload return 503."""

    class FailingStorage(StorageBackend):
        def save(self, storage_key: str, data: bytes) -> str:
            raise StorageError("Disk full")

        def delete(self, storage_key: str) -> None:
            pass

        def exists(self, storage_key: str) -> bool:
            return False

        def get_path(self, storage_key: str) -> str:
            return ""

    set_storage_backend(FailingStorage())

    response = doc_test_client.upload(
        "/api/v1/documents/upload",
        make_pdf_bytes(),
        "fail_storage.pdf",
        headers=auth_headers,
    )
    assert response.status_code == 503
    assert "unavailable" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Migration Test Addition
# ---------------------------------------------------------------------------


def test_document_status_migration_renders_offline() -> None:
    """The Phase 4 migration renders valid SQL for the document status update."""
    import os
    import re
    import subprocess
    import sys
    from pathlib import Path

    repository_root = Path(__file__).resolve().parents[2]
    environment = os.environ.copy()
    environment["ANVEXA_DATABASE_URL"] = (
        "postgresql+psycopg://user:password@localhost:5432/anvexa_db"
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            "backend/alembic.ini",
            "upgrade",
            "20261119_0003",
            "--sql",
        ],
        cwd=repository_root,
        env=environment,
        capture_output=True,
        check=True,
        text=True,
    )

    # Verify the migration updates status and creates new constraint
    assert "UPDATE documents SET processing_status" in result.stdout
    assert "completed" in result.stdout
    assert "validating" in result.stdout
    assert "queued" in result.stdout
