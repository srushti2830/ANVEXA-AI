"""Human review workflow schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    ReviewAction,
    ReviewStatus,
    Verdict,
)


class EvidenceForReview(BaseModel):
    evidence_id: UUID
    source_id: UUID
    publication_title: str
    evidence_text: str
    content_type: str
    section_name: str | None = None
    page_number: int | None = None
    paragraph_number: int | None = None
    source_url: str | None = None
    doi: str | None = None
    publication_year: int | None = None
    relation: str


class ReviewDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    review_id: UUID
    verification_result_id: UUID
    claim_id: UUID
    document_id: UUID
    document_title: str
    filename: str
    claim_text: str
    claim_category: str
    page_number: int | None = None
    paragraph_index: int | None = None
    section_heading: str | None = None
    ai_verdict: Verdict
    final_verdict: Verdict | None = None
    ai_explanation: str
    confidence: float | None = None
    confidence_label: str | None = None
    requires_human_review: bool
    review_status: ReviewStatus
    assigned_reviewer_id: UUID | None = None
    supporting_evidence: list[EvidenceForReview] = Field(default_factory=list)
    contradicting_evidence: list[EvidenceForReview] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    structured_analysis: dict[str, object] = Field(default_factory=dict)
    created_at: datetime


class ReviewQueueItem(BaseModel):
    review_id: UUID
    verification_result_id: UUID
    claim_id: UUID
    document_id: UUID
    document_title: str
    claim_text: str
    ai_verdict: Verdict
    final_verdict: Verdict | None = None
    confidence: float | None = None
    confidence_label: str | None = None
    review_status: ReviewStatus
    requires_human_review: bool
    created_at: datetime


class PaginationMeta(BaseModel):
    total: int
    page: int
    per_page: int
    total_pages: int


class ReviewQueueResponse(BaseModel):
    reviews: list[ReviewQueueItem]
    pagination: PaginationMeta


class ReviewSubmitRequest(BaseModel):
    verdict: Verdict
    explanation: str = Field(min_length=10, max_length=5000)
    notes: str | None = Field(default=None, max_length=5000)
    evidence_ids: list[UUID] = Field(default_factory=list)


class ReviewHistoryItem(BaseModel):
    id: UUID
    verification_result_id: UUID
    reviewer_id: UUID
    action: ReviewAction
    original_ai_verdict: Verdict
    human_verdict: Verdict
    reviewer_comment: str | None = None
    is_resolved: bool
    reviewed_at: datetime


class ReviewHistoryResponse(BaseModel):
    review_id: UUID
    history: list[ReviewHistoryItem]
    pagination: PaginationMeta


class ReviewInvestigationRequest(BaseModel):
    explanation: str = Field(min_length=10, max_length=5000)
    evidence_ids: list[UUID] = Field(default_factory=list)
    notes: str | None = Field(default=None, max_length=5000)
