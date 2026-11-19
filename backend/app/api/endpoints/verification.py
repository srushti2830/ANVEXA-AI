"""Claim verification API endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.database.session import get_db
from app.models.user import User
from app.schemas.verification import (
    DocumentVerificationResponse,
    VerificationHistoryResponse,
    VerificationResponse,
)
from app.services.verdict_classifier.verification_service import (
    get_claim_verification,
    get_document_verification,
    get_verification_history,
    verify_claim,
    verify_document,
)

claim_router = APIRouter(tags=["verification"])
document_router = APIRouter(prefix="/documents", tags=["verification"])


@claim_router.post(
    "/claims/{claim_id}/verify",
    response_model=VerificationResponse,
)
def verify_one_claim(
    claim_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return verify_claim(claim_id, current_user, db)


@document_router.post(
    "/{document_id}/verify",
)
def verify_one_document(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return verify_document(document_id, current_user, db)


@claim_router.get(
    "/claims/{claim_id}/verification",
    response_model=VerificationResponse,
)
def get_one_verification(
    claim_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_claim_verification(claim_id, current_user, db)


@document_router.get(
    "/{document_id}/verification",
)
def get_one_document_verification(
    document_id: UUID,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_document_verification(
        document_id,
        current_user,
        db,
        page,
        per_page,
    )


@claim_router.get(
    "/claims/{claim_id}/verification-history",
    response_model=VerificationHistoryResponse,
)
def get_claim_verification_history(
    claim_id: UUID,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_verification_history(
        claim_id,
        current_user,
        db,
        page,
        per_page,
    )
