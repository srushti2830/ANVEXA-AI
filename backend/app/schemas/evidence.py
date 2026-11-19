"""Pydantic schemas for evidence extraction and retrieval."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import EvidenceContentType


class EvidenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    evidence_id: UUID
    claim_id: UUID | None = None
    source_id: UUID
    publication_title: str
    evidence_text: str
    content_type: EvidenceContentType
    section_name: str | None = None
    page_number: int | None = None
    paragraph_number: int | None = None
    source_url: str | None = None
    doi: str | None = None
    extraction_method: str | None = None
    similarity_score: float | None = None
    created_at: datetime


class PaginationMeta(BaseModel):
    total: int
    page: int
    per_page: int
    total_pages: int


class ClaimEvidenceResponse(BaseModel):
    claim_id: UUID
    evidence: list[EvidenceResponse]
    total_evidence: int
    extraction_status: str


class DocumentEvidenceResponse(BaseModel):
    document_id: UUID
    version_id: UUID
    evidence: list[EvidenceResponse]
    total_evidence: int
    extraction_status: str
    pagination: PaginationMeta
