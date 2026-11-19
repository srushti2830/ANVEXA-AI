from __future__ import annotations

from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    Uuid,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database.base import Base
from backend.app.models.enums import (
    CitationStyle,
    ClaimType,
    DocumentStatus,
    enum_column,
)
from backend.app.models.mixins import TimestampMixin, UUIDPrimaryKey


class Document(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("size_bytes > 0", name="ck_documents_size_positive"),
        CheckConstraint(
            "length(content_sha256) = 64",
            name="ck_documents_sha256_length",
        ),
        UniqueConstraint(
            "owner_id",
            "content_sha256",
            name="uq_documents_owner_content",
        ),
        Index("ix_documents_owner_created", "owner_id", "created_at"),
    )

    owner_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    media_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[DocumentStatus] = mapped_column(
        enum_column(DocumentStatus, "document_status"),
        nullable=False,
        default=DocumentStatus.UPLOADED,
        server_default=text("'uploaded'"),
    )

    owner: Mapped[User] = relationship(back_populates="documents")
    versions: Mapped[list[DocumentVersion]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentVersion.version_number",
    )
    reports: Mapped[list[Report]] = relationship(back_populates="document")
    processing_jobs: Mapped[list[ProcessingJob]] = relationship(
        back_populates="document"
    )


class DocumentVersion(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "document_versions"
    __table_args__ = (
        CheckConstraint("version_number > 0", name="ck_document_versions_positive"),
        UniqueConstraint(
            "document_id",
            "version_number",
            name="uq_document_versions_number",
        ),
    )

    document_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)

    document: Mapped[Document] = relationship(back_populates="versions")
    pages: Mapped[list[DocumentPage]] = relationship(
        back_populates="document_version",
        cascade="all, delete-orphan",
        order_by="DocumentPage.page_number",
    )
    claims: Mapped[list[Claim]] = relationship(
        back_populates="document_version",
        cascade="all, delete-orphan",
    )
    citations: Mapped[list[Citation]] = relationship(
        back_populates="document_version",
        cascade="all, delete-orphan",
    )
    verification_results: Mapped[list[VerificationResult]] = relationship(
        back_populates="document_version",
        cascade="all, delete-orphan",
    )
    reference_issues: Mapped[list[ReferenceIssue]] = relationship(
        back_populates="document_version",
        cascade="all, delete-orphan",
    )
    processing_jobs: Mapped[list[ProcessingJob]] = relationship(
        back_populates="document_version"
    )
    reports: Mapped[list[Report]] = relationship(back_populates="document_version")


class DocumentPage(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "document_pages"
    __table_args__ = (
        CheckConstraint("page_number > 0", name="ck_document_pages_positive"),
        UniqueConstraint(
            "document_version_id",
            "page_number",
            name="uq_document_pages_version_page",
        ),
    )

    document_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        JSON,
        nullable=False,
        default=dict,
    )

    document_version: Mapped[DocumentVersion] = relationship(back_populates="pages")
    claims: Mapped[list[Claim]] = relationship(back_populates="page")


class Claim(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "claims"
    __table_args__ = (
        CheckConstraint(
            "paragraph_index IS NULL OR paragraph_index >= 0",
            name="ck_claims_paragraph_nonnegative",
        ),
        Index("ix_claims_version_page", "document_version_id", "page_id"),
    )

    document_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    page_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("document_pages.id", ondelete="SET NULL"),
    )
    paragraph_index: Mapped[int | None] = mapped_column(Integer)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    context_text: Mapped[str | None] = mapped_column(Text)
    claim_type: Mapped[ClaimType] = mapped_column(
        enum_column(ClaimType, "claim_type"),
        nullable=False,
        default=ClaimType.OTHER,
        server_default=text("'other'"),
    )
    requires_external_verification: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    extraction_method: Mapped[str | None] = mapped_column(String(120))

    document_version: Mapped[DocumentVersion] = relationship(back_populates="claims")
    page: Mapped[DocumentPage | None] = relationship(back_populates="claims")
    citation_links: Mapped[list[ClaimCitation]] = relationship(
        back_populates="claim",
        cascade="all, delete-orphan",
    )
    verification_results: Mapped[list[VerificationResult]] = relationship(
        back_populates="claim",
        cascade="all, delete-orphan",
        order_by="VerificationResult.created_at",
    )
    feedback: Mapped[list[UserFeedback]] = relationship(back_populates="claim")


class Citation(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "citations"
    __table_args__ = (
        Index("ix_citations_version", "document_version_id"),
        Index("ix_citations_doi", "doi"),
        Index("ix_citations_research_source", "research_source_id"),
    )

    document_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    research_source_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("research_sources.id", ondelete="SET NULL"),
    )
    label: Mapped[str | None] = mapped_column(String(120))
    style: Mapped[CitationStyle] = mapped_column(
        enum_column(CitationStyle, "citation_style"),
        nullable=False,
        default=CitationStyle.UNKNOWN,
        server_default=text("'unknown'"),
    )
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(String(1000))
    authors: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    publication_year: Mapped[int | None] = mapped_column(Integer)
    doi: Mapped[str | None] = mapped_column(String(255))
    url: Mapped[str | None] = mapped_column(String(2048))
    page_number: Mapped[int | None] = mapped_column(Integer)
    is_bibliography_entry: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )

    document_version: Mapped[DocumentVersion] = relationship(back_populates="citations")
    research_source: Mapped[ResearchSource | None] = relationship(
        back_populates="citations"
    )
    claim_links: Mapped[list[ClaimCitation]] = relationship(
        back_populates="citation",
        cascade="all, delete-orphan",
    )
    reference_issues: Mapped[list[ReferenceIssue]] = relationship(
        back_populates="citation"
    )


class ClaimCitation(Base, UUIDPrimaryKey):
    __tablename__ = "claim_citations"
    __table_args__ = (
        CheckConstraint(
            "page_number IS NULL OR page_number > 0",
            name="ck_claim_citations_page_positive",
        ),
        CheckConstraint(
            "character_offset IS NULL OR character_offset >= 0",
            name="ck_claim_citations_offset_nonnegative",
        ),
        Index("ix_claim_citations_claim", "claim_id"),
        Index("ix_claim_citations_citation", "citation_id"),
    )

    claim_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("claims.id", ondelete="CASCADE"),
        nullable=False,
    )
    citation_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("citations.id", ondelete="CASCADE"),
        nullable=False,
    )
    citation_text: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer)
    character_offset: Mapped[int | None] = mapped_column(Integer)
    mapping_method: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        default="explicit",
        server_default=text("'explicit'"),
    )

    claim: Mapped[Claim] = relationship(back_populates="citation_links")
    citation: Mapped[Citation] = relationship(back_populates="claim_links")
