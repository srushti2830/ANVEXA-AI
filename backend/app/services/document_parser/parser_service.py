"""Document parsing orchestration service.

Coordinates reading a stored document, running the unified parser,
persisting DocumentVersion + DocumentPage records, and updating
document status through the lifecycle.
"""

from __future__ import annotations

import logging
import math
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette import status

from app.models.document import Document, DocumentPage, DocumentVersion
from app.models.enums import DocumentStatus
from app.models.user import User
from app.services.document_parser.parser import parse_document as unified_parse
from app.services.document_service import get_storage_backend
from app.services.document_storage.storage_service import StorageError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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

    # Transition → PROCESSING
    doc.processing_status = DocumentStatus.PROCESSING
    db.commit()

    # 2. Run unified parser
    try:
        result = unified_parse(
            data=data,
            filename=doc.filename,
            file_type=doc.file_type,
            enable_ocr=True,
        )
    except ValueError as exc:
        logger.error("Parse failed for document %s: %s", document_id, exc)
        doc.processing_status = DocumentStatus.FAILED
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Document parsing failed: {exc}",
        ) from exc

    # 3. Determine version number
    max_version = db.execute(
        select(DocumentVersion.version_number)
        .where(DocumentVersion.document_id == doc.id)
        .order_by(DocumentVersion.version_number.desc())
        .limit(1)
    ).scalar_one_or_none()
    next_version = (max_version or 0) + 1

    # 4. Create DocumentVersion
    version = DocumentVersion(
        document_id=doc.id,
        version_number=next_version,
        storage_key=doc.storage_path,
        content_sha256=doc.file_hash,
    )
    db.add(version)
    db.flush()  # get version.id

    # 5. Create DocumentPage records
    total_chars = 0
    for page_data in result.page_texts:
        page_text = page_data.get("text", "")
        page_meta = page_data.get("metadata", {})
        page = DocumentPage(
            document_id=doc.id,
            document_version_id=version.id,
            page_number=page_data["page_number"],
            extracted_text=page_text,
            metadata_json=page_meta,
        )
        db.add(page)
        total_chars += len(page_text)

    # 6. Transition → COMPLETED
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
        "Document parsed: id=%s version=%d pages=%d chars=%d method=%s duration=%dms",
        document_id,
        next_version,
        result.total_pages,
        total_chars,
        result.extraction_method,
        result.processing_duration_ms,
    )

    return {
        "document_id": str(doc.id),
        "filename": doc.filename,
        "file_type": doc.file_type,
        "version_id": str(version.id),
        "version_number": next_version,
        "total_pages": result.total_pages,
        "total_characters": total_chars,
        "extraction_method": result.extraction_method,
        "ocr_applied": result.ocr_applied,
        "ocr_pages": result.ocr_pages,
        "headings": result.headings,
        "character_count": total_chars,
        "word_count": result.word_count,
        "processing_duration_ms": result.processing_duration_ms,
        "processing_status": doc.processing_status.value,
        "warnings": result.warnings,
        "metadata": result.metadata,
    }


def get_parsed_content(
    document_id: UUID,
    current_user: User,
    db: Session,
) -> dict:
    """Return full parsed content for the latest version of a document."""
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
            detail="Document has not been parsed yet. Use POST /parse first.",
        )

    # Fetch all pages
    pages = list(
        db.execute(
            select(DocumentPage)
            .where(DocumentPage.document_version_id == version.id)
            .order_by(DocumentPage.page_number.asc())
        ).scalars().all()
    )

    full_text = "\n\n".join(p.extracted_text for p in pages)

    # Collect OCR pages
    ocr_pages = [
        p.page_number for p in pages
        if p.metadata_json.get("extraction_method") == "tesseract_ocr"
    ]

    # Headings from metadata (if stored)
    headings = [
        p.metadata_json.get("headings", []) for p in pages
    ]

    return {
        "document_id": str(doc.id),
        "filename": doc.filename,
        "file_type": doc.file_type,
        "version_id": str(version.id),
        "version_number": version.version_number,
        "total_pages": len(pages),
        "total_characters": len(full_text),
        "extracted_text": full_text,
        "pages": [
            {
                "page_number": p.page_number,
                "text": p.extracted_text,
                "char_count": len(p.extracted_text),
                "word_count": len(p.extracted_text.split()) if p.extracted_text else 0,
                "metadata": p.metadata_json,
            }
            for p in pages
        ],
        "ocr_pages": ocr_pages,
        "processing_status": doc.processing_status.value,
    }
