"""Document management API endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, UploadFile, File, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.database.session import get_db
from app.models.enums import DocumentStatus
from app.models.user import User
from app.schemas.document import (
    DocumentListResponse,
    DocumentQueryParams,
    DocumentResponse,
    DocumentStatusResponse,
    DocumentUploadResponse,
)
from app.services.document_service import (
    delete_user_document,
    get_document_status,
    get_user_document,
    list_user_documents,
    upload_document,
)

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a document",
    description="Upload a PDF or DOCX document. The file is validated, hashed, and stored.",
)
def upload(
    file: UploadFile = File(..., description="PDF or DOCX file"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    return upload_document(file, current_user, db, settings)


@router.get(
    "",
    response_model=DocumentListResponse,
    summary="List documents",
    description="List the current user's documents with pagination, search, and filtering.",
)
def list_documents(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None, description="Search by filename"),
    file_type: str | None = Query(default=None, description="Filter by MIME type"),
    doc_status: DocumentStatus | None = Query(
        default=None, alias="status", description="Filter by processing status"
    ),
    sort_order: str = Query(default="desc", pattern=r"^(asc|desc)$"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    params = DocumentQueryParams(
        page=page,
        per_page=per_page,
        search=search,
        file_type=file_type,
        status=doc_status,
        sort_order=sort_order,
    )
    return list_user_documents(current_user, params, db)


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    summary="Get document details",
)
def get_document(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_user_document(document_id, current_user, db)


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete a document",
)
def delete_document(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return delete_user_document(document_id, current_user, db)


@router.get(
    "/{document_id}/status",
    response_model=DocumentStatusResponse,
    summary="Get document processing status",
)
def document_status(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_document_status(document_id, current_user, db)
