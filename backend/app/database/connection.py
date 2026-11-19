from functools import lru_cache

from sqlalchemy import Engine, create_engine

from app.core.config import get_settings


def create_database_engine(
    database_url: str,
    pool_size: int = 5,
    max_overflow: int = 10,
) -> Engine:
    return create_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=pool_size,
        max_overflow=max_overflow,
    )


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    database_url = get_settings().database_url
    if database_url is None:
        raise RuntimeError(
            "ANVEXA_DATABASE_URL must be configured before using the database."
        )
    settings = get_settings()
    return create_database_engine(
        database_url.get_secret_value(),
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
    )
