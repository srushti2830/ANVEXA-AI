from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import Boolean, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship, synonym

from app.database.base import Base
from app.models.enums import UserRole, enum_column
from app.models.mixins import TimestampMixin, UUIDPrimaryKey


class User(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email", name="uq_users_email"),)

    email: Mapped[str] = mapped_column(String(320), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    hashed_password: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="",
        server_default=sa.text("''"),
    )
    role: Mapped[UserRole] = mapped_column(
        enum_column(UserRole, "user_role"),
        nullable=False,
        default=UserRole.USER,
        server_default=sa.text("'user'"),
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=sa.text("true"),
    )
    is_verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=sa.text("false"),
    )

    display_name = synonym("full_name")

    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
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
