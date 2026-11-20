import asyncio

import httpx
from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.database import health as database_health
from app.database.connection import create_database_engine
from app.database.session import SessionLocal, get_db
from app.main import create_app


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
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    monkeypatch.setattr(
        "app.database.session.get_engine",
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
    engine = _postgres_health_engine(pgvector_available=True)
    monkeypatch.setattr(database_health, "get_engine", lambda: engine)

    response = get_response(
        create_app(Settings(_env_file=None)),
        "/api/v1/health/database",
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "ok",
        "pgvector": "available",
    }


def test_database_health_reports_missing_pgvector(monkeypatch) -> None:
    engine = _postgres_health_engine(pgvector_available=False)
    monkeypatch.setattr(database_health, "get_engine", lambda: engine)

    response = get_response(
        create_app(Settings(_env_file=None)),
        "/api/v1/health/database",
    )

    assert response.status_code == 503
    assert response.json()["detail"]["database"] == "ok"
    assert response.json()["detail"]["pgvector"] == "unavailable"


def test_sqlite_development_health_does_not_claim_pgvector(
    monkeypatch,
    tmp_path,
) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'health.sqlite3'}"
    settings = Settings(
        _env_file=None,
        dev_database_mode=True,
        dev_sqlite_url=database_url,
    )
    engine = create_database_engine(database_url)
    monkeypatch.setattr(database_health, "get_engine", lambda: engine)
    monkeypatch.setattr(database_health, "get_settings", lambda: settings)

    try:
        response = get_response(
            create_app(settings),
            "/api/v1/health/database",
        )
    finally:
        engine.dispose()

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "ok",
        "pgvector": "not_applicable",
        "vector_search": "development_in_process_cosine",
    }


def _postgres_health_engine(pgvector_available: bool):
    class Result:
        def __init__(self, value):
            self.value = value

        def scalar_one(self):
            return self.value

    class Connection:
        class Dialect:
            name = "postgresql"

        dialect = Dialect()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, statement):
            if "pg_extension" in str(statement):
                return Result(pgvector_available)
            return Result(1)

    class Engine:
        def connect(self):
            return Connection()

    return Engine()


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


def test_database_health_handles_unavailable_psycopg_runtime(monkeypatch) -> None:
    def unavailable_driver():
        raise ImportError("PostgreSQL driver is unavailable")

    monkeypatch.setattr(database_health, "get_engine", unavailable_driver)
    response = get_response(
        create_app(Settings()),
        "/api/v1/health/database",
    )

    assert response.status_code == 503
    assert response.json()["detail"]["database"] == "unavailable"
    assert "PostgreSQL driver is unavailable" not in response.text


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
