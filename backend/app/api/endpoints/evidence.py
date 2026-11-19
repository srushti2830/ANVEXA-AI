"""Evidence extraction and retrieval API endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.database.session import get_db
from app.models.user import User
from app.schemas.evidence import ClaimEvidenceResponse, DocumentEvidenceResponse
from app.services.evidence_engine.evidence_engine import (
    extract_claim_evidence,
    extract_document_evidence,
    list_claim_evidence,
    list_document_evidence,
    list_source_evidence,
)

claim_router = APIRouter(tags=["evidence"])
document_router = APIRouter(prefix="/documents", tags=["evidence"])
source_router = APIRouter(prefix="/sources", tags=["evidence"])


@claim_router.post(
    "/claims/{claim_id}/extract-evidence",
    response_model=ClaimEvidenceResponse,
)
def extract_for_claim(
    claim_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return extract_claim_evidence(claim_id, current_user, db)


@claim_router.get(
    "/claims/{claim_id}/evidence",
    response_model=ClaimEvidenceResponse,
)
def get_claim_evidence(
    claim_id: UUID,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return list_claim_evidence(claim_id, current_user, db, page, per_page)


@source_router.get("/{source_id}/evidence")
def get_source_evidence(
    source_id: UUID,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return list_source_evidence(source_id, current_user, db, page, per_page)


@document_router.post(
    "/{document_id}/extract-evidence",
)
def extract_for_document(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return extract_document_evidence(document_id, current_user, db)


@document_router.get(
    "/{document_id}/evidence",
    response_model=DocumentEvidenceResponse,
)
def get_document_evidence(
    document_id: UUID,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return list_document_evidence(document_id, current_user, db, page, per_page)
