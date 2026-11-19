"""Pydantic schemas for claim extraction API responses."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ClaimType, ExtractionStatus


class ExtractedClaimItem(BaseModel):
    claim_type: str
    claim_text: str
    original_sentence: str
    document_id: UUID
    page_number: int | None = None
    paragraph_index: int | None = None
    section_heading: str | None = None
    extraction_method: str
    extraction_confidence: float = Field(ge=0.0, le=1.0)
    citation_markers: list[str] = Field(default_factory=list)
    is_verifiable: bool = True
    extraction_reason: str
    created_at: datetime


class ClaimResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    document_version_id: UUID
    claim_type: ClaimType
    claim_text: str
    original_sentence: str
    page_number: int | None = None
    paragraph_index: int | None = None
    section_heading: str | None = None
    extraction_method: str | None = None
    extraction_confidence: float | None = None
    citation_markers: list[str] = Field(default_factory=list)
    is_verifiable: bool = True
    extraction_reason: str | None = None
    extraction_status: ExtractionStatus
    created_at: datetime


class ClaimListResponse(BaseModel):
    document_id: UUID
    version_id: UUID
    claims: list[ClaimResponse]
    pagination: dict[str, int]


class ClaimExtractionResponse(BaseModel):
    document_id: UUID
    version_id: UUID
    version_number: int
    extracted_count: int
    extraction_method: str
    processing_status: ExtractionStatus
    claims: list[ClaimResponse]
