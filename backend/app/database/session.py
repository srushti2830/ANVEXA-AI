from collections.abc import Generator

from sqlalchemy.orm import Session, sessionmaker

from backend.app.database.connection import get_engine

SessionLocal = sessionmaker(autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    with SessionLocal(bind=get_engine()) as session:
        yield session
