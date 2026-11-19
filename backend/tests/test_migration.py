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
            "head",
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
