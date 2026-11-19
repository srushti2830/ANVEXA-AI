import os
import re
import subprocess
import sys
from pathlib import Path


def test_initial_migration_renders_postgresql_schema_offline() -> None:
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
            "20261119_0001",
            "--sql",
        ],
        cwd=repository_root,
        env=environment,
        capture_output=True,
        check=True,
        text=True,
    )

    assert len(re.findall(r"(?m)^CREATE TABLE ", result.stdout)) == 21
    assert "CREATE EXTENSION IF NOT EXISTS vector" in result.stdout
    assert "USING hnsw" in result.stdout
    assert "CREATE TABLE claims" in result.stdout
    assert "CREATE TABLE verification_results" in result.stdout


def test_auth_migration_renders_postgresql_schema_offline() -> None:
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
            "head",
            "--sql",
        ],
        cwd=repository_root,
        env=environment,
        capture_output=True,
        check=True,
        text=True,
    )

    assert len(re.findall(r"(?m)^CREATE TABLE ", result.stdout)) == 22
    assert "CREATE TABLE refresh_tokens" in result.stdout
    assert "ALTER TABLE users ADD COLUMN hashed_password" in result.stdout
    assert "ALTER TABLE users ADD COLUMN role" in result.stdout
    assert "ALTER TABLE users ADD COLUMN is_active" in result.stdout
    assert "ALTER TABLE users ADD COLUMN is_verified" in result.stdout
    assert "CREATE UNIQUE INDEX ix_refresh_tokens_token_hash" in result.stdout


def test_phase10_through_phase13_migrations_render_offline() -> None:
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
            "head",
            "--sql",
        ],
        cwd=repository_root,
        env=environment,
        capture_output=True,
        check=True,
        text=True,
    )
    assert "request_investigation" in result.stdout
    assert "ALTER TABLE review_history DROP CONSTRAINT review_action" in result.stdout
    assert "action IN ('accept_ai', 'reject_ai'" in result.stdout
    assert "ALTER TABLE reports DROP CONSTRAINT report_format" in result.stdout
    assert "format IN ('pdf', 'csv', 'json')" in result.stdout
