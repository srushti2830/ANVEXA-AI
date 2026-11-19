"""Pydantic response schemas for citation detection and mapping."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import CitationMappingStatus, CitationStyle


class CitationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    document_version_id: UUID
    citation_type: CitationStyle
    citation_text: str
    original_marker: str | None = None
    normalized_marker: str | None = None
    reference_number: str | None = None
    authors: list[str] = Field(default_factory=list)
    publication_year: int | None = None
    publication_title: str | None = None
    journal_or_conference: str | None = None
    volume: str | None = None
    issue: str | None = None
    page_range: str | None = None
    doi: str | None = None
    url: str | None = None
    page_number: int | None = None
    paragraph_number: int | None = None
    is_bibliography_entry: bool
    extraction_method: str | None = None
    created_at: datetime


class CitationMappingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    claim_id: UUID
    citation_id: UUID
    citation_text: str
    normalized_marker: str | None = None
    page_number: int | None = None
    paragraph_number: int | None = None
    mapping_status: CitationMappingStatus
    mapping_method: str
    character_offset: int | None = None


class PaginationMeta(BaseModel):
    total: int
    page: int
    per_page: int
    total_pages: int


class DocumentCitationListResponse(BaseModel):
    document_id: UUID
    version_id: UUID
    citations: list[CitationResponse]
    pagination: PaginationMeta


class CitationDetectionResponse(BaseModel):
    document_id: UUID
    version_id: UUID
    version_number: int
    detected_count: int
    reference_count: int
    mapping_count: int
    extraction_method: str
    citations: list[CitationResponse]
