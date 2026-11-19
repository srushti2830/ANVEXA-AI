"""Pydantic response schemas for research source retrieval."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import RetrievalStatus, SourceVersionType


class SourceVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    version_type: SourceVersionType
    version_url: str | None = None
    content_sha256: str | None = None
    published_at: datetime | None = None
    full_text_available: bool
    metadata_json: dict[str, object] = Field(
        default_factory=dict,
        serialization_alias="metadata",
    )
    created_at: datetime


class ResearchSourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    doi: str | None = None
    title: str
    authors: list[str] = Field(default_factory=list)
    publication_year: int | None = None
    journal: str | None = None
    source_url: str | None = None
    abstract: str | None = None
    retrieval_status: RetrievalStatus
    is_retracted: bool
    metadata_json: dict[str, object] = Field(
        default_factory=dict,
        serialization_alias="metadata",
    )
    created_at: datetime
    versions: list[SourceVersionResponse] = Field(default_factory=list)


class PaginationMeta(BaseModel):
    total: int
    page: int
    per_page: int
    total_pages: int


class DocumentSourceListResponse(BaseModel):
    document_id: UUID
    version_id: UUID
    sources: list[ResearchSourceResponse]
    pagination: PaginationMeta


class SourceRetrievalResponse(BaseModel):
    document_id: UUID
    version_id: UUID
    retrieved_count: int
    unavailable_count: int
    duplicate_count: int
    extraction_method: str
    sources: list[ResearchSourceResponse]
