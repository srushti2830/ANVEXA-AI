from collections.abc import Sequence
from typing import Any, TypeVar
from uuid import UUID

from sqlalchemy import Select, inspect, select
from sqlalchemy.orm import Session

from backend.app.core.embedding import EMBEDDING_DIMENSION
from backend.app.database.base import Base
from backend.app.models.research import Embedding, EvidencePassage

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
    session.delete(record)
    session.flush()


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
        .order_by(distance)
        .limit(limit)
    )


def search_similar_evidence(
    session: Session,
    query_vector: Sequence[float],
    limit: int = 10,
) -> list[EvidencePassage]:
    statement = similar_evidence_query(query_vector, limit)
    return list(session.scalars(statement).all())
