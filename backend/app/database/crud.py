from typing import Any, TypeVar
from uuid import UUID

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from backend.app.database.base import Base

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
