"""Report and analytics schemas for Phase 13."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import Verdict


class ReportEvidenceResponse(BaseModel):
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


class ReportCitationResponse(BaseModel):
    citation_id: UUID
    citation_text: str
    original_marker: str | None = None
    normalized_marker: str | None = None
    style: str
    reference_number: str | None = None
    page_number: int | None = None
    paragraph_number: int | None = None


class ClaimReportResponse(BaseModel):
    claim_id: UUID
    claim_text: str
    claim_category: str
    page_number: int | None = None
    paragraph_index: int | None = None
    section_heading: str | None = None
    citation_markers: list[str] = Field(default_factory=list)
    ai_verdict: Verdict | None = None
    human_verdict: Verdict | None = None
    final_verdict: Verdict | None = None
    result_label: str
    confidence_label: str | None = None
    confidence_score: float | None = None
    explanation: str | None = None
    limitations: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    supporting_evidence: list[ReportEvidenceResponse] = Field(default_factory=list)
    contradicting_evidence: list[ReportEvidenceResponse] = Field(default_factory=list)
    citations: list[ReportCitationResponse] = Field(default_factory=list)
    review_status: str
    human_review_history: list[dict[str, object]] = Field(default_factory=list)


class VerdictDistribution(BaseModel):
    supported: int = 0
    partly_supported: int = 0
    unsupported: int = 0
    contradictory: int = 0
    possibly_outdated: int = 0
    needs_review: int = 0


class DocumentReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    document_id: UUID
    document_title: str
    filename: str
    processing_status: str
    document_version_id: UUID | None = None
    document_version_number: int | None = None
    uploaded_at: datetime
    generated_at: datetime
    total_claims: int
    total_citations: int
    total_sources: int
    total_evidence_passages: int
    verified_claims: int
    claims_awaiting_review: int
    unresolved_claims: int
    human_reviewed_claims: int
    verdict_distribution: VerdictDistribution
    claim_reports: list[ClaimReportResponse]
    limitations: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    disclaimer: str


class AnalyticsOverviewResponse(BaseModel):
    documents_uploaded: int
    documents_processed: int
    claims_extracted: int
    citations_detected: int
    sources_retrieved: int
    evidence_passages_extracted: int
    claims_verified: int
    verdict_distribution: VerdictDistribution
    human_review_completion_rate: float
    claims_awaiting_review: int
    claims_requiring_investigation: int


class DocumentAnalyticsResponse(BaseModel):
    document_id: UUID
    documents_uploaded: int
    documents_processed: int
    claims_extracted: int
    citations_detected: int
    sources_retrieved: int
    evidence_passages_extracted: int
    claims_verified: int
    verdict_distribution: VerdictDistribution
    human_review_completion_rate: float
    claims_awaiting_review: int
    claims_requiring_investigation: int
