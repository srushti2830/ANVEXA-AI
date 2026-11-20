from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import URL, inspect, select, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.embedding import EMBEDDING_DIMENSION, EMBEDDING_MODEL
from app.database import connection, health as database_health
from app.database.base import Base
from app.database.crud import search_similar_evidence
from app.database.connection import create_database_engine
from app.models import (
    Embedding,
    EvidencePassage,
    ResearchSource,
    SourceVersion,
    User,
)
from app.models.enums import EvidenceContentType, SourceVersionType


def test_development_database_mode_is_explicit_and_development_only() -> None:
    default_settings = Settings(_env_file=None)
    assert default_settings.dev_database_mode is False
    assert default_settings.active_database_url is None
    settings = Settings(
        dev_database_mode=True,
        dev_sqlite_url="sqlite+pysqlite:///:memory:",
    )
    assert settings.active_database_url == "sqlite+pysqlite:///:memory:"

    with pytest.raises(ValidationError, match="only when"):
        Settings(
            environment="production",
            dev_database_mode=True,
            dev_sqlite_url="sqlite+pysqlite:///:memory:",
        )
    with pytest.raises(ValidationError, match="SQLite SQLAlchemy URL"):
        Settings(
            dev_database_mode=True,
            dev_sqlite_url="postgresql+psycopg://user:pass@localhost/db",
        )


def test_sqlite_database_url_is_rejected_without_explicit_dev_mode(
    monkeypatch,
    tmp_path,
) -> None:
    settings = Settings(
        database_url=f"sqlite+pysqlite:///{(tmp_path / 'not-enabled.db').as_posix()}"
    )
    monkeypatch.setattr(connection, "get_settings", lambda: settings)
    connection.get_engine.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="ANVEXA_DEV_DATABASE_MODE"):
            connection.get_engine()
    finally:
        connection.get_engine.cache_clear()


def test_dev_database_creates_schema_and_persists_users(
    monkeypatch,
    tmp_path,
) -> None:
    database_path = tmp_path / "anvexa-dev.sqlite3"
    database_url = URL.create(
        "sqlite+pysqlite",
        database=str(database_path),
    ).render_as_string(hide_password=False)
    settings = Settings(
        dev_database_mode=True,
        dev_sqlite_url=database_url,
    )
    monkeypatch.setattr(connection, "get_settings", lambda: settings)
    connection.get_engine.cache_clear()
    engine = None
    try:
        engine = connection.get_engine()
        assert engine.dialect.name == "sqlite"
        assert inspect(engine).has_table("documents")
        assert not any(
            index["name"] == "ix_embeddings_vector_hnsw"
            for index in inspect(engine).get_indexes("embeddings")
        )
        with engine.connect() as database_connection:
            assert database_connection.execute(
                text("PRAGMA foreign_keys")
            ).scalar_one() == 1
        with Session(engine) as session:
            user = User(
                id=uuid4(),
                email="sqlite-persistent@example.test",
                full_name="SQLite Development User",
                hashed_password="test-hash",
            )
            session.add(user)
            session.commit()
        engine.dispose()
        engine = None
        connection.get_engine.cache_clear()

        reopened_engine = connection.get_engine()
        with Session(reopened_engine) as session:
            saved_user = session.scalars(
                select(User).where(
                    User.email == "sqlite-persistent@example.test"
                )
            ).one()
            assert saved_user.full_name == "SQLite Development User"
        reopened_engine.dispose()
    finally:
        if engine is not None:
            engine.dispose()
        connection.get_engine.cache_clear()


def test_development_health_identifies_sqlite_without_claiming_pgvector(
    monkeypatch,
    tmp_path,
) -> None:
    database_url = URL.create(
        "sqlite+pysqlite",
        database=str(tmp_path / "health.sqlite3"),
    ).render_as_string(hide_password=False)
    settings = Settings(
        dev_database_mode=True,
        dev_sqlite_url=database_url,
    )
    engine = create_database_engine(database_url)
    monkeypatch.setattr(database_health, "get_settings", lambda: settings)
    monkeypatch.setattr(database_health, "get_engine", lambda: engine)
    try:
        health = database_health.check_database_health()
        assert health.connected is True
        assert health.pgvector_available is False
        assert health.development_sqlite is True
    finally:
        engine.dispose()


def test_sqlite_vector_search_uses_in_process_cosine_similarity() -> None:
    engine = create_database_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    query_vector = [0.0] * EMBEDDING_DIMENSION
    matching_vector = [0.0] * EMBEDDING_DIMENSION
    unrelated_vector = [0.0] * EMBEDDING_DIMENSION
    query_vector[0] = 1.0
    matching_vector[0] = 1.0
    unrelated_vector[1] = 1.0

    try:
        with Session(engine) as session:
            source = ResearchSource(
                title="Local vector search test source",
                authors=[],
                metadata_json={},
            )
            session.add(source)
            session.flush()
            version = SourceVersion(
                source_id=source.id,
                version_type=SourceVersionType.PUBLISHED,
                metadata_json={},
            )
            session.add(version)
            session.flush()
            matching_passage = EvidencePassage(
                source_id=source.id,
                source_version_id=version.id,
                passage_index=0,
                passage_text="Matching evidence passage",
                content_type=EvidenceContentType.ABSTRACT,
            )
            unrelated_passage = EvidencePassage(
                source_id=source.id,
                source_version_id=version.id,
                passage_index=1,
                passage_text="Unrelated evidence passage",
                content_type=EvidenceContentType.ABSTRACT,
            )
            session.add_all([matching_passage, unrelated_passage])
            session.flush()
            session.add_all([
                Embedding(
                    evidence_passage_id=matching_passage.id,
                    vector=matching_vector,
                    model_name=EMBEDDING_MODEL,
                ),
                Embedding(
                    evidence_passage_id=unrelated_passage.id,
                    vector=unrelated_vector,
                    model_name=EMBEDDING_MODEL,
                ),
            ])
            session.commit()

            results = search_similar_evidence(session, query_vector, limit=2)
            assert [passage.id for passage in results] == [
                matching_passage.id,
                unrelated_passage.id,
            ]
    finally:
        engine.dispose()
