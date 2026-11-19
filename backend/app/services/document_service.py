"""Document management service — upload, list, retrieve, delete operations."""

from __future__ import annotations

import hashlib
import logging
import math
import mimetypes
import os
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.config import Settings, get_settings
from backend.app.models.document import Document
from backend.app.models.enums import DocumentStatus
from backend.app.models.user import User
from backend.app.schemas.document import (
    DocumentListResponse,
    DocumentQueryParams,
    DocumentResponse,
    DocumentStatusResponse,
    DocumentUploadResponse,
    PaginationMeta,
)
from backend.app.services.document_storage.local_storage import LocalStorageBackend
from backend.app.services.document_storage.storage_service import (
    StorageBackend,
    StorageError,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# File-type magic bytes signatures
# ---------------------------------------------------------------------------

# PDF: starts with %PDF
PDF_MAGIC = b"%PDF"

# DOCX: a ZIP archive starting with PK\x03\x04
ZIP_MAGIC = b"PK\x03\x04"

# Allowed MIME types mapped from extensions
EXTENSION_MIME_MAP: dict[str, str] = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def validate_file_extension(filename: str, allowed: list[str]) -> str:
    """Return the lowercased extension if allowed, else raise 422."""
    _, ext = os.path.splitext(filename)
    ext = ext.lower()
    if ext not in allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(allowed)}",
        )
    return ext


def validate_file_content(data: bytes, extension: str) -> None:
    """Validate file magic bytes match the claimed extension."""
    if not data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Uploaded file is empty",
        )

    if extension == ".pdf":
        if not data[:4].startswith(PDF_MAGIC):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="File content does not match PDF format",
            )
    elif extension == ".docx":
        if not data[:4].startswith(ZIP_MAGIC):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="File content does not match DOCX format",
            )


def validate_file_size(size: int, max_size: int) -> None:
    """Reject files exceeding the configured max size."""
    if size > max_size:
        max_mb = max_size / (1024 * 1024)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size ({size} bytes) exceeds maximum allowed ({max_mb:.0f} MB)",
        )


def compute_sha256(data: bytes) -> str:
    """Return hex-encoded SHA-256 hash of *data*."""
    return hashlib.sha256(data).hexdigest()


def validate_mime_type(filename: str, extension: str) -> str:
    """Determine MIME type from extension; fall back to mapping."""
    guessed, _ = mimetypes.guess_type(filename)
    expected = EXTENSION_MIME_MAP.get(extension)
    return guessed or expected or "application/octet-stream"


# ---------------------------------------------------------------------------
# Storage singleton (lazily initialised)
# ---------------------------------------------------------------------------

_storage_backend: StorageBackend | None = None


def get_storage_backend(settings: Settings | None = None) -> StorageBackend:
    """Return (and cache) the storage backend."""
    global _storage_backend
    if _storage_backend is None:
        if settings is None:
            settings = get_settings()
        _storage_backend = LocalStorageBackend(settings.document_storage_path)
    return _storage_backend


def reset_storage_backend() -> None:
    """Reset cached backend — useful for testing."""
    global _storage_backend
    _storage_backend = None


def set_storage_backend(backend: StorageBackend) -> None:
    """Inject a custom storage backend — useful for testing."""
    global _storage_backend
    _storage_backend = backend


# ---------------------------------------------------------------------------
# Service functions
# ---------------------------------------------------------------------------


def upload_document(
    file: UploadFile,
    current_user: User,
    db: Session,
    settings: Settings | None = None,
) -> DocumentUploadResponse:
    """Validate, store, and persist an uploaded document."""
    if settings is None:
        settings = get_settings()

    # 1. Read file content
    data = file.file.read()
    file.file.seek(0)

    # 2. Extension validation
    filename = file.filename or "untitled"
    ext = validate_file_extension(filename, settings.allowed_file_extensions)

    # 3. Content validation (magic bytes)
    validate_file_content(data, ext)

    # 4. Size validation
    validate_file_size(len(data), settings.max_upload_size_bytes)

    # 5. Compute SHA-256 hash
    file_hash = compute_sha256(data)

    # 6. Duplicate detection (same user + same hash)
    existing = db.execute(
        select(Document).where(
            Document.user_id == current_user.id,
            Document.file_hash == file_hash,
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Duplicate document detected. Existing document ID: {existing.id}",
        )

    # 7. Generate unique storage key
    storage_key = f"{uuid4().hex}{ext}"

    # 8. Store file
    storage = get_storage_backend(settings)
    try:
        storage_path = storage.save(storage_key, data)
    except StorageError as exc:
        logger.error("Storage failure during upload: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="File storage is temporarily unavailable",
        ) from exc

    # 9. Determine MIME / file_type
    mime = validate_mime_type(filename, ext)

    # 10. Create database record
    now = datetime.now(timezone.utc)
    doc = Document(
        user_id=current_user.id,
        title=os.path.splitext(filename)[0],
        filename=filename,
        storage_path=storage_key,  # Store key, NOT full path
        file_hash=file_hash,
        file_type=mime,
        file_size=len(data),
        processing_status=DocumentStatus.UPLOADED,
        uploaded_at=now,
    )

    try:
        db.add(doc)
        db.commit()
        db.refresh(doc)
    except IntegrityError:
        db.rollback()
        # Clean up stored file
        try:
            storage.delete(storage_key)
        except StorageError:
            pass
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Duplicate document detected",
        )
    except Exception:
        db.rollback()
        try:
            storage.delete(storage_key)
        except StorageError:
            pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save document record",
        )

    logger.info(
        "Document uploaded: id=%s user=%s filename=%s",
        doc.id,
        current_user.id,
        filename,
    )

    return DocumentUploadResponse(
        id=doc.id,
        filename=doc.filename,
        file_type=doc.file_type,
        file_size=doc.file_size,
        file_hash=doc.file_hash,
        processing_status=doc.processing_status,
        uploaded_at=doc.uploaded_at,
        message="Document uploaded successfully",
    )


def list_user_documents(
    current_user: User,
    params: DocumentQueryParams,
    db: Session,
) -> DocumentListResponse:
    """Return paginated, filtered, searchable document list for the user."""
    query = select(Document).where(Document.user_id == current_user.id)

    # Filters
    if params.search:
        query = query.where(Document.filename.ilike(f"%{params.search}%"))
    if params.file_type:
        query = query.where(Document.file_type.ilike(f"%{params.file_type}%"))
    if params.status:
        query = query.where(Document.processing_status == params.status)

    # Count total (before pagination)
    count_query = select(func.count()).select_from(query.subquery())
    total = db.execute(count_query).scalar() or 0

    # Sorting
    if params.sort_order == "asc":
        query = query.order_by(Document.uploaded_at.asc())
    else:
        query = query.order_by(Document.uploaded_at.desc())

    # Pagination
    offset = (params.page - 1) * params.per_page
    query = query.offset(offset).limit(params.per_page)

    documents = list(db.execute(query).scalars().all())
    total_pages = max(1, math.ceil(total / params.per_page))

    return DocumentListResponse(
        documents=[DocumentResponse.model_validate(d) for d in documents],
        pagination=PaginationMeta(
            total=total,
            page=params.page,
            per_page=params.per_page,
            total_pages=total_pages,
        ),
    )


def get_user_document(
    document_id: UUID,
    current_user: User,
    db: Session,
) -> DocumentResponse:
    """Retrieve a single document with ownership enforcement."""
    doc = db.execute(
        select(Document).where(Document.id == document_id)
    ).scalar_one_or_none()

    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    # Ownership check — admins can access any document
    from backend.app.api.dependencies import verify_resource_ownership
    verify_resource_ownership(doc.user_id, current_user)

    return DocumentResponse.model_validate(doc)


def get_document_status(
    document_id: UUID,
    current_user: User,
    db: Session,
) -> DocumentStatusResponse:
    """Return lightweight processing status for a document."""
    doc = db.execute(
        select(Document).where(Document.id == document_id)
    ).scalar_one_or_none()

    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    from backend.app.api.dependencies import verify_resource_ownership
    verify_resource_ownership(doc.user_id, current_user)

    return DocumentStatusResponse(
        id=doc.id,
        processing_status=doc.processing_status,
    )


def delete_user_document(
    document_id: UUID,
    current_user: User,
    db: Session,
    settings: Settings | None = None,
) -> dict[str, str]:
    """Delete a document record and its stored file."""
    doc = db.execute(
        select(Document).where(Document.id == document_id)
    ).scalar_one_or_none()

    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    from backend.app.api.dependencies import verify_resource_ownership
    verify_resource_ownership(doc.user_id, current_user)

    storage_key = doc.storage_path

    # Delete DB record first
    db.delete(doc)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete document record",
        )

    # Then delete file (best-effort)
    if settings is None:
        settings = get_settings()
    storage = get_storage_backend(settings)
    try:
        storage.delete(storage_key)
    except StorageError as exc:
        logger.warning("Failed to delete file for document %s: %s", document_id, exc)

    logger.info("Document deleted: id=%s user=%s", document_id, current_user.id)
    return {"message": f"Document {document_id} deleted successfully"}
