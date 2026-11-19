from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Table,
    Text,
    Uuid,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, synonym

from app.database.base import Base
from app.models.enums import (
    ConfidenceLabel,
    EvidenceRelation,
    IssueCertainty,
    ProcessingJobType,
    ProcessingStatus,
    ReferenceIssueType,
    ReportFormat,
    ReviewAction,
    Verdict,
    VerificationStatus,
    enum_column,
)
from app.models.mixins import TimestampMixin, UUIDPrimaryKey


review_evidence = Table(
    "review_evidence",
    Base.metadata,
    Column(
        "review_id",
        Uuid(as_uuid=True),
        ForeignKey("review_history.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "evidence_passage_id",
        Uuid(as_uuid=True),
        ForeignKey("evidence_passages.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class VerificationResult(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "verification_results"
    __table_args__ = (
        Index("ix_verification_results_claim_created", "claim_id", "created_at"),
        CheckConstraint(
            "confidence_score IS NULL OR "
            "(confidence_score >= 0 AND confidence_score <= 1)",
            name="ck_verification_results_confidence",
        ),
    )

    claim_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("claims.id", ondelete="RESTRICT"),
        nullable=False,
    )
    document_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    verdict: Mapped[Verdict] = mapped_column(
        enum_column(Verdict, "verification_verdict"),
        nullable=False,
    )
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[ConfidenceLabel | None] = mapped_column(
        enum_column(ConfidenceLabel, "confidence_label"),
    )
    confidence_score: Mapped[float | None] = mapped_column(Float)
    verification_status: Mapped[VerificationStatus] = mapped_column(
        enum_column(VerificationStatus, "verification_status"),
        nullable=False,
        default=VerificationStatus.COMPLETED,
        server_default=text("'completed'"),
    )
    model_provider: Mapped[str] = mapped_column(String(100), nullable=False)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(120))
    verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    claim: Mapped[Claim] = relationship(back_populates="verification_results")
    document_version: Mapped[DocumentVersion] = relationship(
        back_populates="verification_results"
    )
    evidence: Mapped[list[VerificationEvidence]] = relationship(
        back_populates="verification_result",
        cascade="all, delete-orphan",
    )
    reviews: Mapped[list[ReviewHistory]] = relationship(
        back_populates="verification_result",
        order_by="ReviewHistory.reviewed_at",
    )
    feedback: Mapped[list[UserFeedback]] = relationship(
        back_populates="verification_result"
    )


class VerificationEvidence(Base, UUIDPrimaryKey):
    __tablename__ = "verification_evidence"
    __table_args__ = (
        CheckConstraint(
            "relevance_score IS NULL OR "
            "(relevance_score >= 0 AND relevance_score <= 1)",
            name="ck_verification_evidence_relevance",
        ),
        UniqueConstraint(
            "verification_result_id",
            "evidence_passage_id",
            name="uq_verification_evidence_result_passage",
        ),
        Index("ix_verification_evidence_result", "verification_result_id"),
    )

    verification_result_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("verification_results.id", ondelete="CASCADE"),
        nullable=False,
    )
    evidence_passage_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("evidence_passages.id", ondelete="RESTRICT"),
        nullable=False,
    )
    relation: Mapped[EvidenceRelation] = mapped_column(
        enum_column(EvidenceRelation, "evidence_relation"),
        nullable=False,
    )
    relevance_score: Mapped[float | None] = mapped_column(Float)
    rationale: Mapped[str | None] = mapped_column(Text)

    verification_result: Mapped[VerificationResult] = relationship(
        back_populates="evidence"
    )
    evidence_passage: Mapped[EvidencePassage] = relationship(
        back_populates="verification_evidence"
    )


class ReferenceIssue(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "reference_issues"
    __table_args__ = (
        CheckConstraint(
            "citation_id IS NOT NULL OR source_id IS NOT NULL",
            name="ck_reference_issues_has_reference",
        ),
        Index(
            "ix_reference_issues_version_type",
            "document_version_id",
            "issue_type",
        ),
    )

    document_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    citation_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("citations.id", ondelete="SET NULL"),
    )
    source_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("research_sources.id", ondelete="SET NULL"),
    )
    issue_type: Mapped[ReferenceIssueType] = mapped_column(
        enum_column(ReferenceIssueType, "reference_issue_type"),
        nullable=False,
    )
    certainty: Mapped[IssueCertainty] = mapped_column(
        enum_column(IssueCertainty, "issue_certainty"),
        nullable=False,
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict[str, object]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )

    document_version: Mapped[DocumentVersion] = relationship(
        back_populates="reference_issues"
    )
    citation: Mapped[Citation | None] = relationship(
        back_populates="reference_issues"
    )
    source: Mapped[ResearchSource | None] = relationship(
        back_populates="reference_issues"
    )


class ReviewHistory(Base, UUIDPrimaryKey):
    __tablename__ = "review_history"
    __table_args__ = (
        Index(
            "ix_review_history_result_created",
            "verification_result_id",
            "reviewed_at",
        ),
        Index("ix_review_history_reviewer", "reviewer_id"),
    )

    verification_result_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("verification_results.id", ondelete="RESTRICT"),
        nullable=False,
    )
    reviewer_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    action: Mapped[ReviewAction] = mapped_column(
        enum_column(ReviewAction, "review_action"),
        nullable=False,
    )
    original_ai_verdict: Mapped[Verdict] = mapped_column(
        enum_column(Verdict, "review_original_verdict"),
        nullable=False,
    )
    original_verdict = synonym("original_ai_verdict")
    human_verdict: Mapped[Verdict] = mapped_column(
        enum_column(Verdict, "review_final_verdict"),
        nullable=False,
    )
    final_verdict = synonym("human_verdict")
    reviewer_comment: Mapped[str | None] = mapped_column(Text)
    comment = synonym("reviewer_comment")
    is_resolved: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    created_at = synonym("reviewed_at")

    verification_result: Mapped[VerificationResult] = relationship(
        back_populates="reviews"
    )
    reviewer: Mapped[User] = relationship(
        back_populates="reviews",
        foreign_keys=[reviewer_id],
    )
    additional_evidence: Mapped[list[EvidencePassage]] = relationship(
        secondary=review_evidence,
    )


class Report(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "reports"
    __table_args__ = (
        Index("ix_reports_owner_created", "owner_id", "created_at"),
    )

    owner_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    format: Mapped[ReportFormat] = mapped_column(
        enum_column(ReportFormat, "report_format"),
        nullable=False,
    )
    status: Mapped[ProcessingStatus] = mapped_column(
        enum_column(ProcessingStatus, "report_status"),
        nullable=False,
        default=ProcessingStatus.QUEUED,
        server_default=text("'queued'"),
    )
    storage_key: Mapped[str | None] = mapped_column(String(1024))
    error_message: Mapped[str | None] = mapped_column(Text)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    owner: Mapped[User] = relationship(back_populates="reports")
    document: Mapped[Document] = relationship(back_populates="reports")
    document_version: Mapped[DocumentVersion] = relationship(back_populates="reports")


class ProcessingJob(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "processing_jobs"
    __table_args__ = (
        CheckConstraint(
            "progress BETWEEN 0 AND 100",
            name="ck_processing_jobs_progress",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_processing_jobs_attempts"),
        UniqueConstraint(
            "owner_id",
            "idempotency_key",
            name="uq_processing_jobs_owner_idempotency",
        ),
        Index("ix_processing_jobs_status_created", "status", "created_at"),
    )

    owner_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
    )
    document_version_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
    )
    job_type: Mapped[ProcessingJobType] = mapped_column(
        enum_column(ProcessingJobType, "processing_job_type"),
        nullable=False,
    )
    status: Mapped[ProcessingStatus] = mapped_column(
        enum_column(ProcessingStatus, "processing_job_status"),
        nullable=False,
        default=ProcessingStatus.QUEUED,
        server_default=text("'queued'"),
    )
    progress: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(255))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at = synonym("completed_at")

    owner: Mapped[User] = relationship(back_populates="processing_jobs")
    document: Mapped[Document | None] = relationship(
        back_populates="processing_jobs"
    )
    document_version: Mapped[DocumentVersion | None] = relationship(
        back_populates="processing_jobs"
    )
