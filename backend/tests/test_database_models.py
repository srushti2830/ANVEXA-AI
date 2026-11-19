from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.embedding import EMBEDDING_DIMENSION, EMBEDDING_MODEL
from backend.app.core.config import Settings
from backend.app.database.base import Base
from backend.app.database.crud import (
    create_record,
    delete_record,
    get_claims_by_document,
    get_citations_by_document,
    get_record,
    get_verification_results_by_claim,
    list_documents,
    similar_evidence_query,
    update_record,
)
from backend.app.database.connection import create_database_engine
from backend.app.models import (
    Claim,
    Citation,
    Document,
    DocumentPage,
    DocumentVersion,
    Embedding,
    ReviewHistory,
    User,
    VerificationResult,
)
from backend.app.models.enums import (
    CitationStyle,
    ClaimType,
    DocumentStatus,
    ReviewAction,
    Verdict,
)


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


def test_database_engine_enables_pre_ping(tmp_path) -> None:
    engine = create_database_engine(
        f"sqlite+pysqlite:///{tmp_path.as_posix()}/test.db"
    )
    try:
        assert engine.dialect.name == "postgresql"
        assert engine.pool._pre_ping
    finally:
        engine.dispose()


def test_database_url_is_redacted_from_settings_repr() -> None:
    secret = "db-password"
    settings = Settings(
        database_url=f"postgresql+psycopg://user:{secret}@localhost/anvexa_db"
    )

    assert settings.database_url is not None
    assert secret in settings.database_url.get_secret_value()
    assert secret not in repr(settings)


def test_semantic_search_compiles_to_pgvector_cosine_query() -> None:
    statement = similar_evidence_query([0.0] * EMBEDDING_DIMENSION)

    assert "<=>" in str(statement.compile(dialect=postgresql.dialect()))


@pytest.mark.parametrize(
    ("vector", "limit", "message"),
    [
        ([0.0], 10, "exactly 384"),
        ([0.0] * EMBEDDING_DIMENSION, 0, "between 1 and 100"),
        ([0.0] * EMBEDDING_DIMENSION, 101, "between 1 and 100"),
    ],
)
def test_semantic_search_validates_vector_and_limit(
    vector: list[float],
    limit: int,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        similar_evidence_query(vector, limit)


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
    updated = get_record(db_session, Document, document_id)
    assert updated is not None
    assert updated.title == "Updated article"

    with pytest.raises(ValueError, match="primary-key"):
        update_record(db_session, loaded, id=UUID(int=0))

    delete_record(db_session, loaded)
    db_session.commit()
    assert get_record(db_session, Document, document_id) is None


def test_document_version_and_page_relationships(db_session: Session) -> None:
    user = create_record(
        db_session,
        User,
        email="pages@example.test",
        hashed_password="not-a-real-password-hash",
        full_name="Owner",
    )
    document = create_record(
        db_session,
        Document,
        user_id=user.id,
        title="Page relationships",
        filename="pages.pdf",
        storage_path="documents/pages.pdf",
        file_hash="c" * 64,
        file_type="application/pdf",
        file_size=64,
    )
    version = create_record(
        db_session,
        DocumentVersion,
        document_id=document.id,
        version_number=1,
        storage_key="documents/pages-v1.pdf",
        content_sha256="c" * 64,
    )
    page = create_record(
        db_session,
        DocumentPage,
        document_id=document.id,
        document_version_id=version.id,
        page_number=1,
        extracted_text="Extracted page text",
    )
    db_session.commit()

    assert page.document_version.document is document
    assert document.pages == [page]


def test_document_listing_is_user_scoped_and_paginated(db_session: Session) -> None:
    first_user = create_record(
        db_session,
        User,
        email="first@example.test",
        hashed_password="not-a-real-password-hash",
        full_name="First",
    )
    second_user = create_record(
        db_session,
        User,
        email="second@example.test",
        hashed_password="not-a-real-password-hash",
        full_name="Second",
    )
    for user, hash_character in ((first_user, "d"), (first_user, "e"), (second_user, "f")):
        create_record(
            db_session,
            Document,
            user_id=user.id,
            title="Scoped document",
            filename="paper.pdf",
            storage_path=f"documents/{hash_character}.pdf",
            file_hash=hash_character * 64,
            file_type="application/pdf",
            file_size=64,
            processing_status=DocumentStatus.READY,
        )
    db_session.commit()

    documents = list_documents(
        db_session,
        first_user.id,
        offset=1,
        limit=1,
        processing_status=DocumentStatus.READY,
    )

    assert len(documents) == 1
    assert documents[0].user_id == first_user.id


def test_document_crud_filters_by_document_and_claim(db_session: Session) -> None:
    user = create_record(
        db_session,
        User,
        email="queries@example.test",
        hashed_password="not-a-real-password-hash",
        full_name="Owner",
    )
    document = create_record(
        db_session,
        Document,
        user_id=user.id,
        title="Query document",
        filename="query.pdf",
        storage_path="documents/query.pdf",
        file_hash="g" * 64,
        file_type="application/pdf",
        file_size=64,
    )
    version = create_record(
        db_session,
        DocumentVersion,
        document_id=document.id,
        version_number=1,
        storage_key="documents/query-v1.pdf",
        content_sha256="g" * 64,
    )
    claim = create_record(
        db_session,
        Claim,
        document_id=document.id,
        document_version_id=version.id,
        original_text="The study reports a result.",
        claim_type=ClaimType.DESCRIPTIVE,
    )
    citation = create_record(
        db_session,
        Citation,
        document_id=document.id,
        document_version_id=version.id,
        citation_text="Reference one",
        citation_type=CitationStyle.NUMERIC,
    )
    verification = create_record(
        db_session,
        VerificationResult,
        claim_id=claim.id,
        document_version_id=version.id,
        verdict=Verdict.NEEDS_REVIEW,
        explanation="No evidence has been reviewed.",
        model_provider="test",
        model_name="test-model",
    )
    review = create_record(
        db_session,
        ReviewHistory,
        verification_result_id=verification.id,
        reviewer_id=user.id,
        action=ReviewAction.CHANGE_VERDICT,
        original_ai_verdict=Verdict.NEEDS_REVIEW,
        human_verdict=Verdict.SUPPORTED,
        reviewer_comment="Reviewed with additional context.",
    )
    db_session.commit()

    assert get_claims_by_document(db_session, document.id) == [claim]
    assert get_citations_by_document(db_session, document.id) == [citation]
    assert get_verification_results_by_claim(db_session, claim.id) == [verification]
    assert review.original_ai_verdict == verification.verdict
    assert review.human_verdict == Verdict.SUPPORTED
    with pytest.raises(ValueError, match="cannot be deleted"):
        delete_record(db_session, verification)


def test_duplicate_document_content_is_rejected_per_owner(
    db_session: Session,
) -> None:
    user = create_record(
        db_session,
        User,
        email="duplicate@example.test",
        hashed_password="not-a-real-password-hash",
        display_name="Owner",
    )
    document_values = {
        "owner_id": user.id,
        "title": "First upload",
        "original_filename": "paper.pdf",
        "storage_key": "documents/paper.pdf",
        "content_sha256": "b" * 64,
        "media_type": "application/pdf",
        "size_bytes": 64,
    }
    create_record(db_session, Document, **document_values)
    db_session.commit()

    with pytest.raises(IntegrityError):
        create_record(
            db_session,
            Document,
            **{**document_values, "title": "Duplicate upload"},
        )
    db_session.rollback()
