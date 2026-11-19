"""Pydantic schemas for document parsing API endpoints."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class PageMetadata(BaseModel):
    char_count: int = 0
    word_count: int = 0
    width_pt: float | None = None
    height_pt: float | None = None
    has_images: bool | None = None


class ParsedPageResponse(BaseModel):
    page_number: int
    text: str
    metadata: dict[str, object] = Field(default_factory=dict)


class ParseResultResponse(BaseModel):
    document_id: UUID
    version_id: UUID
    version_number: int
    total_pages: int
    total_characters: int
    processing_status: str
    metadata: dict[str, object] = Field(default_factory=dict)


class PaginationMeta(BaseModel):
    total: int
    page: int
    per_page: int
    total_pages: int


class DocumentPagesResponse(BaseModel):
    document_id: UUID
    version_id: UUID
    version_number: int
    pages: list[ParsedPageResponse]
    pagination: PaginationMeta


class SinglePageResponse(BaseModel):
    document_id: UUID
    version_id: UUID
    page_number: int
    text: str
    metadata: dict[str, object] = Field(default_factory=dict)


class FullTextResponse(BaseModel):
    document_id: UUID
    version_id: UUID
    version_number: int
    total_pages: int
    total_characters: int
    text: str
