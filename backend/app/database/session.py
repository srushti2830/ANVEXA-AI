from collections.abc import Generator

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, sessionmaker

from app.database.connection import get_engine

SessionLocal = sessionmaker(autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """Provide a transactional database session.

    Raises HTTP 503 if the database is not configured or unreachable,
    instead of letting a raw RuntimeError bubble up as a 500.
    """
    try:
        engine = get_engine()
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is not available. Please check server configuration.",
        )

    with SessionLocal(bind=engine) as session:
        yield session
