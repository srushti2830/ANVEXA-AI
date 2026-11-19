"""Citation detection and mapping API endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.database.session import get_db
from app.models.document import Claim, ClaimCitation, Citation, Document, DocumentVersion
from app.models.user import User
from app.schemas.citations import (
    CitationDetectionResponse,
    CitationMappingResponse,
    DocumentCitationListResponse,
)
from app.services.citation_detector.citation_detector import detect_citations
from app.api.dependencies import verify_resource_ownership

document_router = APIRouter(prefix="/documents", tags=["citations"])
claim_router = APIRouter(tags=["citations"])


@document_router.post(
    "/{document_id}/detect-citations",
    response_model=CitationDetectionResponse,
    summary="Detect and map citations in a parsed document",
)
def detect_document_citations(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return detect_citations(document_id, current_user, db)


@document_router.get(
    "/{document_id}/citations",
    response_model=DocumentCitationListResponse,
    summary="List detected citations and reference entries",
)
def list_document_citations(
    document_id: UUID,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = db.execute(select(Document).where(Document.id == document_id)).scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    verify_resource_ownership(doc.user_id, current_user)
    version = db.execute(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == doc.id)
        .order_by(DocumentVersion.version_number.desc())
        .limit(1)
    ).scalar_one_or_none()
    if version is None:
        raise HTTPException(status_code=404, detail="Document has not been parsed yet")
    statement = select(Citation).where(Citation.document_version_id == version.id)
    all_citations = list(db.execute(statement.order_by(Citation.created_at)).scalars().all())
    citations = all_citations[(page - 1) * per_page:page * per_page]
    total = len(all_citations)
    return {
        "document_id": doc.id,
        "version_id": version.id,
        "citations": citations,
        "pagination": {
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": (total + per_page - 1) // per_page,
        },
    }


@claim_router.get(
    "/claims/{claim_id}/citations",
    response_model=list[CitationMappingResponse],
    summary="List citation mappings for a claim",
)
def list_claim_citations(
    claim_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    claim = db.execute(select(Claim).where(Claim.id == claim_id)).scalar_one_or_none()
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    doc = db.execute(select(Document).where(Document.id == claim.document_id)).scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    verify_resource_ownership(doc.user_id, current_user)
    links = list(db.execute(
        select(ClaimCitation)
        .where(ClaimCitation.claim_id == claim_id)
        .order_by(ClaimCitation.id)
    ).scalars().all())
    return links


@document_router.get(
    "/{document_id}/citation-mapping",
    summary="Return claim-to-citation mappings for a document",
)
def get_document_citation_mapping(
    document_id: UUID,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = db.execute(select(Document).where(Document.id == document_id)).scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    verify_resource_ownership(doc.user_id, current_user)
    version = db.execute(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == doc.id)
        .order_by(DocumentVersion.version_number.desc())
        .limit(1)
    ).scalar_one_or_none()
    if version is None:
        raise HTTPException(status_code=404, detail="Document has not been parsed yet")
    statement = (
        select(ClaimCitation)
        .join(Claim, ClaimCitation.claim_id == Claim.id)
        .where(Claim.document_version_id == version.id)
        .order_by(ClaimCitation.id)
    )
    all_links = list(db.execute(statement).scalars().all())
    links = all_links[(page - 1) * per_page:page * per_page]
    total = len(all_links)
    return {
        "document_id": doc.id,
        "version_id": version.id,
        "mappings": links,
        "pagination": {
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": (total + per_page - 1) // per_page,
        },
    }
