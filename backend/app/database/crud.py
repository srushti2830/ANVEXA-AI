from collections.abc import Sequence
from typing import Any, TypeVar
from uuid import UUID

from sqlalchemy import Select, inspect, select
from sqlalchemy.orm import Session

from app.core.embedding import EMBEDDING_DIMENSION, EMBEDDING_MODEL
from app.core.vector_math import cosine_similarity
from app.database.base import Base
from app.models.audit import AuditLog
from app.models.document import Claim, Citation, Document
from app.models.enums import DocumentStatus
from app.models.research import Embedding, EvidencePassage
from app.models.verification import ReviewHistory, VerificationResult

ModelT = TypeVar("ModelT", bound=Base)


def create_record(
    session: Session,
    model: type[ModelT],
    **values: Any,
) -> ModelT:
    record = model(**values)
    session.add(record)
    session.flush()
    return record


def get_record(
    session: Session,
    model: type[ModelT],
    record_id: UUID,
) -> ModelT | None:
    return session.get(model, record_id)


def update_record(
    session: Session,
    record: ModelT,
    **values: Any,
) -> ModelT:
    mapper = inspect(type(record))
    allowed_fields = {
        attribute.key
        for attribute in mapper.column_attrs
        if not any(column.primary_key for column in attribute.columns)
    }
    invalid_fields = values.keys() - allowed_fields
    if invalid_fields:
        names = ", ".join(sorted(invalid_fields))
        raise ValueError(f"Cannot update unmapped or primary-key fields: {names}")

    for field, value in values.items():
        setattr(record, field, value)
    session.flush()
    return record


def delete_record(session: Session, record: ModelT) -> None:
    if isinstance(record, (AuditLog, ReviewHistory, VerificationResult)):
        raise ValueError(
            "Historical verification and audit records cannot be deleted."
        )
    session.delete(record)
    session.flush()


def _validate_pagination(offset: int, limit: int) -> None:
    if offset < 0:
        raise ValueError("Pagination offset cannot be negative.")
    if not 1 <= limit <= 100:
        raise ValueError("Pagination limit must be between 1 and 100.")


def list_documents(
    session: Session,
    user_id: UUID,
    *,
    offset: int = 0,
    limit: int = 50,
    processing_status: DocumentStatus | None = None,
) -> list[Document]:
    _validate_pagination(offset, limit)
    statement = select(Document).where(Document.user_id == user_id)
    if processing_status is not None:
        statement = statement.where(
            Document.processing_status == processing_status
        )
    statement = (
        statement.order_by(Document.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(session.scalars(statement).all())


def get_claims_by_document(
    session: Session,
    document_id: UUID,
    *,
    offset: int = 0,
    limit: int = 100,
) -> list[Claim]:
    _validate_pagination(offset, limit)
    statement = (
        select(Claim)
        .where(Claim.document_id == document_id)
        .order_by(Claim.created_at)
        .offset(offset)
        .limit(limit)
    )
    return list(session.scalars(statement).all())


def get_citations_by_document(
    session: Session,
    document_id: UUID,
    *,
    offset: int = 0,
    limit: int = 100,
) -> list[Citation]:
    _validate_pagination(offset, limit)
    statement = (
        select(Citation)
        .where(Citation.document_id == document_id)
        .order_by(Citation.created_at)
        .offset(offset)
        .limit(limit)
    )
    return list(session.scalars(statement).all())


def get_verification_results_by_claim(
    session: Session,
    claim_id: UUID,
    *,
    offset: int = 0,
    limit: int = 100,
) -> list[VerificationResult]:
    _validate_pagination(offset, limit)
    statement = (
        select(VerificationResult)
        .where(VerificationResult.claim_id == claim_id)
        .order_by(VerificationResult.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(session.scalars(statement).all())


def similar_evidence_query(
    query_vector: Sequence[float],
    limit: int = 10,
) -> Select[tuple[EvidencePassage]]:
    if len(query_vector) != EMBEDDING_DIMENSION:
        raise ValueError(
            f"Embedding must contain exactly {EMBEDDING_DIMENSION} values."
        )
    if not 1 <= limit <= 100:
        raise ValueError("Search limit must be between 1 and 100.")

    distance = Embedding.vector.cosine_distance(list(query_vector))
    return (
        select(EvidencePassage)
        .join(Embedding)
        .where(Embedding.model_name == EMBEDDING_MODEL)
        .order_by(distance)
        .limit(limit)
    )


def search_similar_evidence(
    session: Session,
    query_vector: Sequence[float],
    limit: int = 10,
) -> list[EvidencePassage]:
    statement = similar_evidence_query(query_vector, limit)
    if session.get_bind().dialect.name == "sqlite":
        candidates = session.execute(
            select(EvidencePassage, Embedding.vector)
            .join(
                Embedding,
                Embedding.evidence_passage_id == EvidencePassage.id,
            )
            .where(Embedding.model_name == EMBEDDING_MODEL)
        ).all()
        ranked = sorted(
            (
                (passage, cosine_similarity(query_vector, vector))
                for passage, vector in candidates
            ),
            key=lambda item: item[1],
            reverse=True,
        )
        return [passage for passage, _score in ranked[:limit]]
    return list(session.scalars(statement).all())
