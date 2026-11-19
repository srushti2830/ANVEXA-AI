import asyncio

import httpx
from fastapi import FastAPI
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from backend.app.core.config import Settings
from backend.app.database import health as database_health
from backend.app.database.session import SessionLocal, get_db
from backend.app.main import create_app


def get_response(app: FastAPI, path: str) -> httpx.Response:
    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            return await client.get(path)

    return asyncio.run(request())


def test_session_dependency_uses_injected_engine(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    monkeypatch.setattr(
        "backend.app.database.session.get_engine",
        lambda: engine,
    )
    dependency = get_db()

    session = next(dependency)
    try:
        assert isinstance(session, SessionLocal.class_)
        assert session.get_bind() is engine
    finally:
        dependency.close()
        engine.dispose()


def test_database_health_reports_connection_and_pgvector(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE pg_extension (extname TEXT)"))
        connection.execute(
            text("INSERT INTO pg_extension (extname) VALUES ('vector')")
        )
    monkeypatch.setattr(database_health, "get_engine", lambda: engine)

    response = get_response(
        create_app(Settings()),
        "/api/v1/health/database",
    )
    engine.dispose()

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "ok",
        "pgvector": "available",
    }


def test_database_health_reports_missing_pgvector(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE pg_extension (extname TEXT)"))
    monkeypatch.setattr(database_health, "get_engine", lambda: engine)

    response = get_response(
        create_app(Settings()),
        "/api/v1/health/database",
    )
    engine.dispose()

    assert response.status_code == 503
    assert response.json()["detail"]["database"] == "ok"
    assert response.json()["detail"]["pgvector"] == "unavailable"


def test_database_health_hides_connection_errors(monkeypatch) -> None:
    class FailedEngine:
        def connect(self):
            raise OperationalError(
                "SELECT 1",
                {},
                RuntimeError("sensitive connection detail"),
            )

    monkeypatch.setattr(database_health, "get_engine", FailedEngine)
    response = get_response(
        create_app(Settings()),
        "/api/v1/health/database",
    )

    assert response.status_code == 503
    assert "sensitive connection detail" not in response.text
    assert response.json()["detail"] == {
        "status": "unavailable",
        "database": "unavailable",
        "pgvector": "unknown",
    }


def test_database_health_handles_missing_database_configuration(
    monkeypatch,
) -> None:
    def missing_database_url():
        raise RuntimeError("ANVEXA_DATABASE_URL must be configured")

    monkeypatch.setattr(database_health, "get_engine", missing_database_url)
    response = get_response(
        create_app(Settings()),
        "/api/v1/health/database",
    )

    assert response.status_code == 503
    assert response.json()["detail"]["database"] == "unavailable"
