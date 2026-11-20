from dataclasses import dataclass

from sqlalchemy import text

from app.core.config import get_settings
from app.database.connection import get_engine


@dataclass(frozen=True)
class DatabaseHealth:
    connected: bool
    pgvector_available: bool
    development_sqlite: bool = False


def check_database_health() -> DatabaseHealth:
    with get_engine().connect() as connection:
        connection.execute(text("SELECT 1")).scalar_one()
        if connection.dialect.name == "sqlite":
            if get_settings().dev_database_mode:
                return DatabaseHealth(
                    connected=True,
                    pgvector_available=False,
                    development_sqlite=True,
                )
            return DatabaseHealth(connected=True, pgvector_available=False)
        if connection.dialect.name != "postgresql":
            return DatabaseHealth(connected=True, pgvector_available=False)
        pgvector_available = bool(
            connection.execute(
                text(
                    "SELECT EXISTS ("
                    "SELECT 1 FROM pg_extension WHERE extname = 'vector'"
                    ")"
                )
            ).scalar_one()
        )
    return DatabaseHealth(connected=True, pgvector_available=pgvector_available)
