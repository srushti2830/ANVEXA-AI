from collections.abc import Generator

from sqlalchemy.orm import Session, sessionmaker

from backend.app.database.connection import get_engine


def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    with get_session_factory()() as session:
        yield session
