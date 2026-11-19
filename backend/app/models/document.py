from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    Float,
    String,
    Text,
    Uuid,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, synonym

from app.database.base import Base
from app.models.enums import (
    CitationStyle,
    ClaimType,
    DocumentStatus,
    ExtractionStatus,
    enum_column,
)
from app.models.mixins import TimestampMixin, UUIDPrimaryKey


class Document(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("file_size > 0", name="ck_documents_size_positive"),
        CheckConstraint(
            "length(file_hash) = 64",
            name="ck_documents_sha256_length",
        ),
        UniqueConstraint(
            "user_id",
            "file_hash",
            name="uq_documents_user_file_hash",
        ),
        Index("ix_documents_user_created", "user_id", "created_at"),
        Index("ix_documents_file_hash", "file_hash"),
        Index("ix_documents_processing_status", "processing_status"),
    )

    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    owner_id = synonym("user_id")
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename = synonym("filename")
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    storage_key = synonym("storage_path")
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    content_sha256 = synonym("file_hash")
    file_type: Mapped[str] = mapped_column(String(100), nullable=False)
    media_type = synonym("file_type")
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    size_bytes = synonym("file_size")
    processing_status: Mapped[DocumentStatus] = mapped_column(
        enum_column(DocumentStatus, "document_status"),
        nullable=False,
        default=DocumentStatus.UPLOADED,
        server_default=text("'uploaded'"),
    )
    status = synonym("processing_status")
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    owner: Mapped[User] = relationship(back_populates="documents")
    versions: Mapped[list[DocumentVersion]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentVersion.version_number",
    )
    pages: Mapped[list[DocumentPage]] = relationship(
        secondary="document_versions",
        primaryjoin="Document.id == DocumentVersion.document_id",
        secondaryjoin="DocumentVersion.id == DocumentPage.document_version_id",
        viewonly=True,
    )
    claims: Mapped[list[Claim]] = relationship(
        secondary="document_versions",
        primaryjoin="Document.id == DocumentVersion.document_id",
        secondaryjoin="DocumentVersion.id == Claim.document_version_id",
        viewonly=True,
    )
    citations: Mapped[list[Citation]] = relationship(
        secondary="document_versions",
        primaryjoin="Document.id == DocumentVersion.document_id",
        secondaryjoin="DocumentVersion.id == Citation.document_version_id",
        viewonly=True,
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
        UniqueConstraint(
            "document_id",
            "id",
            name="uq_document_versions_document_id",
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
        ForeignKeyConstraint(
            ["document_id", "document_version_id"],
            ["document_versions.document_id", "document_versions.id"],
            ondelete="CASCADE",
            name="fk_document_pages_document_version",
        ),
    )

    document_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    document_version_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    extracted_text: Mapped[str] = mapped_column(Text, nullable=False)
    text = synonym("extracted_text")
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
            "paragraph_number IS NULL OR paragraph_number >= 0",
            name="ck_claims_paragraph_nonnegative",
        ),
        Index("ix_claims_document_id", "document_id"),
        Index("ix_claims_version_page", "document_version_id", "page_id"),
        ForeignKeyConstraint(
            ["document_id", "document_version_id"],
            ["document_versions.document_id", "document_versions.id"],
            ondelete="CASCADE",
            name="fk_claims_document_version",
        ),
    )

    document_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    document_version_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    page_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("document_pages.id", ondelete="SET NULL"),
    )
    paragraph_number: Mapped[int | None] = mapped_column(Integer)
    paragraph_index = synonym("paragraph_number")
    page_number: Mapped[int | None] = mapped_column(Integer)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    original_sentence = synonym("original_text")
    normalized_text: Mapped[str | None] = mapped_column(Text)
    claim_text = synonym("normalized_text")
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
    is_verifiable = synonym("requires_external_verification")
    extraction_method: Mapped[str | None] = mapped_column(String(120))
    section_heading: Mapped[str | None] = mapped_column(String(500))
    extraction_confidence: Mapped[float | None] = mapped_column(Float)
    citation_markers: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    extraction_reason: Mapped[str | None] = mapped_column(Text)
    extraction_status: Mapped[ExtractionStatus] = mapped_column(
        enum_column(ExtractionStatus, "claim_extraction_status"),
        nullable=False,
        default=ExtractionStatus.PENDING,
        server_default=text("'pending'"),
    )

    document_version: Mapped[DocumentVersion] = relationship(back_populates="claims")
    page: Mapped[DocumentPage | None] = relationship(back_populates="claims")
    citation_links: Mapped[list[ClaimCitation]] = relationship(
        back_populates="claim",
        cascade="all, delete-orphan",
    )
    verification_results: Mapped[list[VerificationResult]] = relationship(
        back_populates="claim",
        order_by="VerificationResult.created_at",
    )
    feedback: Mapped[list[UserFeedback]] = relationship(back_populates="claim")


class Citation(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "citations"
    __table_args__ = (
        Index("ix_citations_document_id", "document_id"),
        Index("ix_citations_version", "document_version_id"),
        Index("ix_citations_doi", "doi"),
        Index("ix_citations_research_source", "research_source_id"),
        ForeignKeyConstraint(
            ["document_id", "document_version_id"],
            ["document_versions.document_id", "document_versions.id"],
            ondelete="CASCADE",
            name="fk_citations_document_version",
        ),
    )

    document_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    document_version_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    research_source_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("research_sources.id", ondelete="SET NULL"),
    )
    reference_number: Mapped[str | None] = mapped_column(String(120))
    label = synonym("reference_number")
    citation_type: Mapped[CitationStyle] = mapped_column(
        enum_column(CitationStyle, "citation_style"),
        nullable=False,
        default=CitationStyle.UNKNOWN,
        server_default=text("'unknown'"),
    )
    style = synonym("citation_type")
    citation_text: Mapped[str] = mapped_column(Text, nullable=False)
    raw_text = synonym("citation_text")
    publication_title: Mapped[str | None] = mapped_column(String(1000))
    title = synonym("publication_title")
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
