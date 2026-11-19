from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from backend.app.core.embedding import EMBEDDING_DIMENSION, EMBEDDING_MODEL
from backend.app.database.base import Base
from backend.app.database.crud import (
    create_record,
    delete_record,
    get_record,
    update_record,
)
from backend.app.models import Document, Embedding, User


@pytest.fixture
def db_session() -> Iterator[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    tables = [
        table
        for table in Base.metadata.sorted_tables
        if table.name != "embeddings"
    ]
    Base.metadata.create_all(engine, tables=tables)

    with Session(engine) as session:
        yield session

    engine.dispose()


def test_core_database_entities_are_registered() -> None:
    expected_tables = {
        "users",
        "documents",
        "document_versions",
        "document_pages",
        "claims",
        "citations",
        "claim_citations",
        "research_sources",
        "source_versions",
        "evidence_passages",
        "embeddings",
        "verification_results",
        "verification_evidence",
        "reference_issues",
        "review_history",
        "reports",
        "processing_jobs",
        "audit_logs",
        "user_feedback",
        "review_evidence",
    }

    assert set(Base.metadata.tables) == expected_tables


def test_embedding_dimension_matches_configured_model() -> None:
    vector_type = Embedding.__table__.c.vector.type

    assert vector_type.dim == EMBEDDING_DIMENSION
    assert EMBEDDING_MODEL == "sentence-transformers/all-MiniLM-L6-v2"
    assert EMBEDDING_DIMENSION == 384


def test_document_crud_round_trip(db_session: Session) -> None:
    user = create_record(
        db_session,
        User,
        email="owner@example.test",
        hashed_password="not-a-real-password-hash",
        display_name="Owner",
    )
    document = create_record(
        db_session,
        Document,
        owner_id=user.id,
        title="Research article",
        original_filename="article.pdf",
        storage_key="documents/article.pdf",
        content_sha256="a" * 64,
        media_type="application/pdf",
        size_bytes=128,
    )
    document_id = document.id
    db_session.commit()

    loaded = get_record(db_session, Document, document_id)
    assert loaded is not None
    assert loaded.owner.email == "owner@example.test"

    update_record(db_session, loaded, title="Updated article")
    db_session.commit()
    assert get_record(db_session, Document, document_id).title == "Updated article"

    with pytest.raises(ValueError, match="primary-key"):
        update_record(db_session, loaded, id=UUID(int=0))

    delete_record(db_session, loaded)
    db_session.commit()
    assert get_record(db_session, Document, document_id) is None
