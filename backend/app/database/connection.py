from functools import lru_cache

from sqlalchemy import Engine, create_engine

from backend.app.core.config import get_settings


def create_database_engine(database_url: str) -> Engine:
    return create_engine(database_url, pool_pre_ping=True)


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    database_url = get_settings().database_url
    if database_url is None:
        raise RuntimeError(
            "ANVEXA_DATABASE_URL must be configured before using the database."
        )
    return create_database_engine(database_url.get_secret_value())
