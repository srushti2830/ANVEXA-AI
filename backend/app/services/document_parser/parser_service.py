"""Document parsing orchestration service.

Coordinates reading a stored document, selecting the right parser,
extracting text, and persisting DocumentVersion + DocumentPage records.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette import status

from app.models.document import Document, DocumentPage, DocumentVersion
from app.models.enums import DocumentStatus
from app.models.user import User
from app.services.document_parser.pdf_parser import parse_pdf
from app.services.document_parser.docx_parser import parse_docx
from app.services.document_service import get_storage_backend
from app.services.document_storage.storage_service import StorageError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MIME_TO_PARSER = {
    "application/pdf": parse_pdf,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": parse_docx,
}


def _get_owned_document(
    document_id: UUID,
    current_user: User,
    db: Session,
) -> Document:
    """Fetch document with ownership enforcement."""
    doc = db.execute(
        select(Document).where(Document.id == document_id)
    ).scalar_one_or_none()

    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    from app.api.dependencies import verify_resource_ownership
    verify_resource_ownership(doc.user_id, current_user)
    return doc


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_document(
    document_id: UUID,
    current_user: User,
    db: Session,
) -> dict:
    """Parse a document: extract text, create version and page records.

    Transitions document status through VALIDATING → PROCESSING → COMPLETED / FAILED.

    Returns a summary dict with version_id, total_pages, and total_chars.
    """
    doc = _get_owned_document(document_id, current_user, db)

    # Guard: only parse documents in a parseable state
    if doc.processing_status not in (
        DocumentStatus.UPLOADED,
        DocumentStatus.FAILED,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Document is in '{doc.processing_status.value}' state. "
                "Only 'uploaded' or 'failed' documents can be parsed."
            ),
        )

    # Transition → VALIDATING
    doc.processing_status = DocumentStatus.VALIDATING
    db.commit()

    # 1. Read file from storage
    storage = get_storage_backend()
    try:
        data = storage.read(doc.storage_path)
    except StorageError as exc:
        logger.error("Storage read failed for document %s: %s", document_id, exc)
        doc.processing_status = DocumentStatus.FAILED
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to read document from storage",
        ) from exc

    # 2. Select parser by MIME type
    parser_fn = _MIME_TO_PARSER.get(doc.file_type)
    if parser_fn is None:
        doc.processing_status = DocumentStatus.FAILED
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"No parser available for file type: {doc.file_type}",
        )

    # Transition → PROCESSING
    doc.processing_status = DocumentStatus.PROCESSING
    db.commit()

    # 3. Parse
    try:
        result = parser_fn(data)
    except ValueError as exc:
        logger.error("Parse failed for document %s: %s", document_id, exc)
        doc.processing_status = DocumentStatus.FAILED
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Document parsing failed: {exc}",
        ) from exc

    # 4. Determine version number
    max_version = db.execute(
        select(DocumentVersion.version_number)
        .where(DocumentVersion.document_id == doc.id)
        .order_by(DocumentVersion.version_number.desc())
        .limit(1)
    ).scalar_one_or_none()
    next_version = (max_version or 0) + 1

    # 5. Create DocumentVersion
    version = DocumentVersion(
        document_id=doc.id,
        version_number=next_version,
        storage_key=doc.storage_path,
        content_sha256=doc.file_hash,
    )
    db.add(version)
    db.flush()  # get version.id

    # 6. Create DocumentPage records
    total_chars = 0
    for parsed_page in result.pages:
        page = DocumentPage(
            document_id=doc.id,
            document_version_id=version.id,
            page_number=parsed_page.page_number,
            extracted_text=parsed_page.text,
            metadata_json=parsed_page.metadata,
        )
        db.add(page)
        total_chars += len(parsed_page.text)

    # 7. Transition → COMPLETED
    doc.processing_status = DocumentStatus.COMPLETED
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        doc.processing_status = DocumentStatus.FAILED
        db.commit()
        logger.error("Failed to persist parse results for %s: %s", document_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save parsing results",
        ) from exc

    logger.info(
        "Document parsed: id=%s version=%d pages=%d chars=%d",
        document_id,
        next_version,
        result.total_pages,
        total_chars,
    )

    return {
        "document_id": doc.id,
        "version_id": version.id,
        "version_number": next_version,
        "total_pages": result.total_pages,
        "total_characters": total_chars,
        "processing_status": doc.processing_status.value,
        "metadata": result.metadata,
    }


def get_document_pages(
    document_id: UUID,
    current_user: User,
    db: Session,
    page: int = 1,
    per_page: int = 20,
) -> dict:
    """Return paginated list of extracted pages for the latest version."""
    doc = _get_owned_document(document_id, current_user, db)

    # Get latest version
    version = db.execute(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == doc.id)
        .order_by(DocumentVersion.version_number.desc())
        .limit(1)
    ).scalar_one_or_none()

    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document has not been parsed yet",
        )

    # Count total pages
    from sqlalchemy import func
    total = db.execute(
        select(func.count())
        .select_from(DocumentPage)
        .where(DocumentPage.document_version_id == version.id)
    ).scalar() or 0

    # Fetch requested page range
    offset = (page - 1) * per_page
    pages = list(
        db.execute(
            select(DocumentPage)
            .where(DocumentPage.document_version_id == version.id)
            .order_by(DocumentPage.page_number.asc())
            .offset(offset)
            .limit(per_page)
        ).scalars().all()
    )

    import math
    total_api_pages = max(1, math.ceil(total / per_page))

    return {
        "document_id": doc.id,
        "version_id": version.id,
        "version_number": version.version_number,
        "pages": [
            {
                "page_number": p.page_number,
                "text": p.extracted_text,
                "metadata": p.metadata_json,
            }
            for p in pages
        ],
        "pagination": {
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": total_api_pages,
        },
    }


def get_document_page(
    document_id: UUID,
    page_number: int,
    current_user: User,
    db: Session,
) -> dict:
    """Return a single extracted page by page number."""
    doc = _get_owned_document(document_id, current_user, db)

    version = db.execute(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == doc.id)
        .order_by(DocumentVersion.version_number.desc())
        .limit(1)
    ).scalar_one_or_none()

    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document has not been parsed yet",
        )

    page = db.execute(
        select(DocumentPage).where(
            DocumentPage.document_version_id == version.id,
            DocumentPage.page_number == page_number,
        )
    ).scalar_one_or_none()

    if page is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Page {page_number} not found",
        )

    return {
        "document_id": doc.id,
        "version_id": version.id,
        "page_number": page.page_number,
        "text": page.extracted_text,
        "metadata": page.metadata_json,
    }


def get_document_full_text(
    document_id: UUID,
    current_user: User,
    db: Session,
) -> dict:
    """Return the full concatenated text of the latest document version."""
    doc = _get_owned_document(document_id, current_user, db)

    version = db.execute(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == doc.id)
        .order_by(DocumentVersion.version_number.desc())
        .limit(1)
    ).scalar_one_or_none()

    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document has not been parsed yet",
        )

    pages = list(
        db.execute(
            select(DocumentPage)
            .where(DocumentPage.document_version_id == version.id)
            .order_by(DocumentPage.page_number.asc())
        ).scalars().all()
    )

    full_text = "\n\n".join(p.extracted_text for p in pages)

    return {
        "document_id": doc.id,
        "version_id": version.id,
        "version_number": version.version_number,
        "total_pages": len(pages),
        "total_characters": len(full_text),
        "text": full_text,
    }
