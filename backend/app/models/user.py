from __future__ import annotations

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship, synonym

from backend.app.database.base import Base
from backend.app.models.mixins import TimestampMixin, UUIDPrimaryKey


class User(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email", name="uq_users_email"),)

    email: Mapped[str] = mapped_column(String(320), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    display_name = synonym("full_name")

    documents: Mapped[list[Document]] = relationship(back_populates="owner")
    reports: Mapped[list[Report]] = relationship(back_populates="owner")
    processing_jobs: Mapped[list[ProcessingJob]] = relationship(
        back_populates="owner"
    )
    reviews: Mapped[list[ReviewHistory]] = relationship(
        back_populates="reviewer",
        foreign_keys="ReviewHistory.reviewer_id",
    )
    audit_logs: Mapped[list[AuditLog]] = relationship(back_populates="actor")
    feedback: Mapped[list[UserFeedback]] = relationship(back_populates="user")
