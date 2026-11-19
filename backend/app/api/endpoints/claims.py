"""Claim extraction API endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.database.session import get_db
from app.models.user import User
from app.schemas.claims import ClaimExtractionResponse, ClaimListResponse, ClaimResponse
from app.services.claim_extractor.claim_extractor import (
    extract_claims,
    get_claim,
    list_claims,
)

router = APIRouter(prefix="/documents", tags=["claims"])
claim_router = APIRouter(tags=["claims"])


@router.post(
    "/{document_id}/extract-claims",
    response_model=ClaimExtractionResponse,
    status_code=status.HTTP_200_OK,
    summary="Extract claims from a parsed document",
)
def extract_document_claims(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return extract_claims(document_id, current_user, db)


@router.get(
    "/{document_id}/claims",
    response_model=ClaimListResponse,
    summary="List claims for a parsed document",
)
def get_document_claims(
    document_id: UUID,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return list_claims(document_id, current_user, db, page, per_page)


@claim_router.get(
    "/claims/{claim_id}",
    response_model=ClaimResponse,
    summary="Get a claim by ID",
)
def get_single_claim(
    claim_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_claim(claim_id, current_user, db)
