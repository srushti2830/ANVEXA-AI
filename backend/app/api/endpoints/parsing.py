"""Document parsing API endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.database.session import get_db
from app.models.user import User
from app.services.document_parser.parser_service import (
    get_parsed_content,
    parse_document,
)

router = APIRouter(prefix="/documents", tags=["parsing"])


@router.post(
    "/{document_id}/parse",
    status_code=status.HTTP_200_OK,
    summary="Parse a document and extract text",
    description=(
        "Runs the document parser on a previously uploaded document. "
        "Extracts text from PDF (via PyMuPDF + optional Tesseract OCR) "
        "or DOCX (via python-docx). Stores extracted pages and updates "
        "the document's processing status."
    ),
)
def parse(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Parse an uploaded document and extract structured text."""
    return parse_document(document_id, current_user, db)


@router.get(
    "/{document_id}/parsed-content",
    status_code=status.HTTP_200_OK,
    summary="Retrieve parsed document content",
    description=(
        "Returns the full extracted text, page-by-page content, and "
        "parsing metadata for a previously parsed document."
    ),
)
def get_content(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve parsed content for a document."""
    return get_parsed_content(document_id, current_user, db)
