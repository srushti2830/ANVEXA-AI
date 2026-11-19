from dataclasses import dataclass

from sqlalchemy import text

from app.database.connection import get_engine


@dataclass(frozen=True)
class DatabaseHealth:
    connected: bool
    pgvector_available: bool


def check_database_health() -> DatabaseHealth:
    with get_engine().connect() as connection:
        connection.execute(text("SELECT 1")).scalar_one()
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
