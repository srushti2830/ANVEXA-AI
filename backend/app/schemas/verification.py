"""Pydantic schemas for claim verification."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    ConfidenceLabel,
    Verdict,
    VerificationStatus,
)


class VerificationAnalysisInput(BaseModel):
    claim_id: UUID
    claim_text: str = Field(min_length=3)
    original_location: dict[str, object] = Field(default_factory=dict)
    claim_category: str
    citation_markers: list[str] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)


class GeminiVerificationOutput(BaseModel):
    verdict: Verdict
    reasoning_summary: str = Field(min_length=3)
    semantic_alignment: str
    context_match: str
    numerical_consistency: str
    causal_consistency: str
    scope_assessment: str
    temporal_assessment: str
    supporting_evidence_ids: list[UUID] = Field(default_factory=list)
    contradicting_evidence_ids: list[UUID] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    requires_human_review: bool = False


class VerificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    claim_id: UUID
    document_version_id: UUID
    verdict: Verdict
    explanation: str
    confidence: ConfidenceLabel | None = None
    confidence_score: float | None = None
    verification_status: VerificationStatus
    structured_analysis: dict[str, object] = Field(default_factory=dict)
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    contradicting_evidence_ids: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    model_name: str
    prompt_version: str
    requires_human_review: bool
    error_message: str | None = None
    verified_at: datetime
    created_at: datetime


class PaginationMeta(BaseModel):
    total: int
    page: int
    per_page: int
    total_pages: int


class VerificationHistoryResponse(BaseModel):
    claim_id: UUID
    verification_results: list[VerificationResponse]
    pagination: PaginationMeta


class DocumentVerificationResponse(BaseModel):
    document_id: UUID
    version_id: UUID
    total_claims: int
    verified_count: int
    failed_count: int
    needs_review_count: int
    results: list[VerificationResponse]


class VerdictClassificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    verification_result_id: UUID
    claim_id: UUID
    ai_verdict: Verdict
    final_verdict: Verdict
    classification_method: str
    classification_reason: str
    classification_confidence: float = Field(ge=0.0, le=1.0)
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    contradicting_evidence_ids: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    requires_human_review: bool
    classified_at: datetime


class HumanVerdictRequest(BaseModel):
    verdict: Verdict
    comment: str = Field(min_length=3, max_length=5000)
    evidence_ids: list[UUID] = Field(default_factory=list)


class HumanVerdictResponse(BaseModel):
    review_id: UUID
    verification_result_id: UUID
    claim_id: UUID
    original_ai_verdict: Verdict
    human_verdict: Verdict
    comment: str
    is_resolved: bool
    reviewed_at: datetime
