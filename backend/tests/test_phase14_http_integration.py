"""Isolated HTTP integration smoke tests for Phase 14."""

from __future__ import annotations

import asyncio
import io
from collections.abc import Iterator

import httpx
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.security import rate_limiter
from app.database.base import Base
from app.database.session import get_db
from app.main import create_app


@pytest.fixture
def http_db_session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record) -> None:
        connection.cursor().execute("PRAGMA foreign_keys=ON")

    tables = [table for table in Base.metadata.sorted_tables if table.name != "embeddings"]
    Base.metadata.create_all(engine, tables=tables)
    with Session(engine) as session:
        yield session
    engine.dispose()


@pytest.fixture
def http_app(http_db_session: Session):
    application = create_app()

    def override_get_db():
        yield http_db_session

    application.dependency_overrides[get_db] = override_get_db
    rate_limiter.reset_all()
    yield application
    application.dependency_overrides.clear()
    rate_limiter.reset_all()


def http_request(app, method: str, path: str, **kwargs) -> httpx.Response:
    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(run())


def test_health_and_openapi_are_reachable(http_app) -> None:
    health = http_request(http_app, "GET", "/health")
    openapi = http_request(http_app, "GET", "/openapi.json")
    assert health.status_code == 200
    assert openapi.status_code == 200
    assert "/api/v1/auth/login" in openapi.json()["paths"]


def test_registration_login_and_authenticated_me(http_app) -> None:
    register = http_request(
        http_app,
        "POST",
        "/api/v1/auth/register",
        json={
            "email": "phase14-http@example.com",
            "full_name": "Phase 14 HTTP",
            "password": "Phase14Test!123",
        },
    )
    assert register.status_code == 201, register.text

    login = http_request(
        http_app,
        "POST",
        "/api/v1/auth/login",
        json={
            "email": "phase14-http@example.com",
            "password": "Phase14Test!123",
        },
    )
    assert login.status_code == 200
    tokens = login.json()
    assert tokens["access_token"]
    assert tokens["refresh_token"]

    me = http_request(
        http_app,
        "GET",
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["email"] == "phase14-http@example.com"


def test_unauthorized_document_upload_is_denied(http_app) -> None:
    response = http_request(
        http_app,
        "POST",
        "/api/v1/documents/upload",
        files={"file": ("sample.pdf", io.BytesIO(b"%PDF-1.4\ntest"), "application/pdf")},
    )
    assert response.status_code == 401


def test_authenticated_document_upload_and_status(http_app) -> None:
    register = http_request(
        http_app,
        "POST",
        "/api/v1/auth/register",
        json={
            "email": "phase14-upload@example.com",
            "full_name": "Phase 14 Upload",
            "password": "Phase14Test!123",
        },
    )
    assert register.status_code == 201
    login = http_request(
        http_app,
        "POST",
        "/api/v1/auth/login",
        json={
            "email": "phase14-upload@example.com",
            "password": "Phase14Test!123",
        },
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\n"
        b"trailer<</Size 4/Root 1 0 R>>\n"
        b"%%EOF\n"
    )
    upload = http_request(
        http_app,
        "POST",
        "/api/v1/documents/upload",
        headers=headers,
        files={"file": ("sample.pdf", io.BytesIO(pdf), "application/pdf")},
    )
    assert upload.status_code == 201
    document_id = upload.json()["id"]

    status = http_request(
        http_app,
        "GET",
        f"/api/v1/documents/{document_id}/status",
        headers=headers,
    )
    assert status.status_code == 200
    assert status.json()["processing_status"] == "uploaded"
