from functools import lru_cache
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings


def create_database_engine(
    database_url: str,
    pool_size: int = 5,
    max_overflow: int = 10,
) -> Engine:
    url = make_url(database_url)
    options: dict[str, object] = {"pool_pre_ping": True}

    if url.get_backend_name() == "sqlite":
        database = url.database
        is_memory_database = database in (None, "", ":memory:")
        if database and database != ":memory:" and not database.startswith("file:"):
            Path(database).parent.mkdir(parents=True, exist_ok=True)
        options["connect_args"] = {"check_same_thread": False}
        if is_memory_database:
            options["poolclass"] = StaticPool
        else:
            options["pool_size"] = pool_size
            options["max_overflow"] = max_overflow
    else:
        options["pool_size"] = pool_size
        options["max_overflow"] = max_overflow

    engine = create_engine(database_url, **options)
    if url.get_backend_name() == "sqlite":
        @event.listens_for(engine, "connect")
        def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    settings = get_settings()
    database_url = settings.active_database_url
    if database_url is None:
        raise RuntimeError(
            "ANVEXA_DATABASE_URL must be configured before using the database."
        )
    url = make_url(database_url)
    if url.get_backend_name() == "sqlite" and not settings.dev_database_mode:
        raise RuntimeError(
            "SQLite requires ANVEXA_DEV_DATABASE_MODE=true and "
            "ANVEXA_ENVIRONMENT=development."
        )

    engine = create_database_engine(
        database_url,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
    )
    if settings.dev_database_mode:
        from app.database.base import Base
        from app.models import __all__ as _registered_models

        Base.metadata.create_all(engine)
    return engine
