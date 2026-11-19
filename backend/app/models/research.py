from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    Uuid,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.embedding import EMBEDDING_DIMENSION, EMBEDDING_MODEL
from backend.app.database.base import Base
from backend.app.models.enums import SourceVersionType, enum_column
from backend.app.models.mixins import TimestampMixin, UUIDPrimaryKey


class ResearchSource(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "research_sources"
    __table_args__ = (
        Index(
            "uq_research_sources_doi",
            "doi",
            unique=True,
            postgresql_where=text("doi IS NOT NULL"),
        ),
        Index("ix_research_sources_title", "title"),
    )

    doi: Mapped[str | None] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(1000), nullable=False)
    authors: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    publication_year: Mapped[int | None] = mapped_column(Integer)
    journal: Mapped[str | None] = mapped_column(String(500))
    canonical_url: Mapped[str | None] = mapped_column(String(2048))
    abstract: Mapped[str | None] = mapped_column(Text)
    is_retracted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
        nullable=False,
        default=dict,
    )

    versions: Mapped[list[SourceVersion]] = relationship(
        back_populates="source",
        cascade="all, delete-orphan",
    )
    citations: Mapped[list[Citation]] = relationship(
        back_populates="research_source"
    )
    reference_issues: Mapped[list[ReferenceIssue]] = relationship(
        back_populates="source"
    )


class SourceVersion(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "source_versions"
    __table_args__ = (
        UniqueConstraint(
            "source_id",
            "content_sha256",
            name="uq_source_versions_content",
        ),
        Index("ix_source_versions_source_published", "source_id", "published_at"),
    )

    source_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("research_sources.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_type: Mapped[SourceVersionType] = mapped_column(
        enum_column(SourceVersionType, "source_version_type"),
        nullable=False,
        default=SourceVersionType.UNKNOWN,
        server_default=text("'unknown'"),
    )
    version_url: Mapped[str | None] = mapped_column(String(2048))
    content_sha256: Mapped[str | None] = mapped_column(String(64))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    full_text_available: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
        nullable=False,
        default=dict,
    )

    source: Mapped[ResearchSource] = relationship(back_populates="versions")
    evidence_passages: Mapped[list[EvidencePassage]] = relationship(
        back_populates="source_version",
        cascade="all, delete-orphan",
        order_by="EvidencePassage.passage_index",
    )


class EvidencePassage(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "evidence_passages"
    __table_args__ = (
        CheckConstraint(
            "page_number IS NULL OR page_number > 0",
            name="ck_evidence_passages_page_positive",
        ),
        CheckConstraint("passage_index >= 0", name="ck_evidence_passages_index"),
        UniqueConstraint(
            "source_version_id",
            "passage_index",
            name="uq_evidence_passages_version_index",
        ),
        Index("ix_evidence_passages_version_section", "source_version_id", "section"),
    )

    source_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("source_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    passage_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    section: Mapped[str | None] = mapped_column(String(300))
    page_number: Mapped[int | None] = mapped_column(Integer)
    location: Mapped[str | None] = mapped_column(String(500))

    source_version: Mapped[SourceVersion] = relationship(
        back_populates="evidence_passages"
    )
    embedding: Mapped[Embedding | None] = relationship(
        back_populates="evidence_passage",
        cascade="all, delete-orphan",
        uselist=False,
    )
    verification_evidence: Mapped[list[VerificationEvidence]] = relationship(
        back_populates="evidence_passage"
    )


class Embedding(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "embeddings"
    __table_args__ = (
        Index(
            "ix_embeddings_vector_hnsw",
            "vector",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"vector": "vector_cosine_ops"},
        ),
    )

    evidence_passage_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("evidence_passages.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    vector: Mapped[list[float]] = mapped_column(
        Vector(EMBEDDING_DIMENSION),
        nullable=False,
    )
    model_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default=EMBEDDING_MODEL,
        server_default=text(f"'{EMBEDDING_MODEL}'"),
    )

    evidence_passage: Mapped[EvidencePassage] = relationship(
        back_populates="embedding"
    )
