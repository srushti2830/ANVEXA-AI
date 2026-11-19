"""Pydantic schemas for document management API endpoints."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.app.models.enums import DocumentStatus


# ---------------------------------------------------------------------------
# Response Schemas
# ---------------------------------------------------------------------------


class DocumentResponse(BaseModel):
    """Public representation of a document — never exposes storage_path."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    title: str
    filename: str
    file_type: str
    file_size: int
    file_hash: str
    processing_status: DocumentStatus
    uploaded_at: datetime
    created_at: datetime
    updated_at: datetime


class DocumentUploadResponse(BaseModel):
    """Response returned after a successful document upload."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    filename: str
    file_type: str
    file_size: int
    file_hash: str
    processing_status: DocumentStatus
    uploaded_at: datetime
    message: str = "Document uploaded successfully"


class DocumentStatusResponse(BaseModel):
    """Lightweight status-only response."""

    id: UUID
    processing_status: DocumentStatus


class PaginationMeta(BaseModel):
    total: int
    page: int
    per_page: int
    total_pages: int


class DocumentListResponse(BaseModel):
    documents: list[DocumentResponse]
    pagination: PaginationMeta


# ---------------------------------------------------------------------------
# Query Parameters (used as dependency models)
# ---------------------------------------------------------------------------


class DocumentQueryParams(BaseModel):
    """Validated query parameters for document listing."""

    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=20, ge=1, le=100)
    search: str | None = None
    file_type: str | None = None
    status: DocumentStatus | None = None
    sort_order: str = Field(default="desc", pattern=r"^(asc|desc)$")
