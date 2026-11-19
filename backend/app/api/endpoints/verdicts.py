"""Final deterministic verdict classification endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_role
from app.database.session import get_db
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.verification import (
    HumanVerdictRequest,
    HumanVerdictResponse,
    VerdictClassificationResponse,
)
from app.services.verdict_classifier.verdict_classifier import (
    classify_claim,
    classify_document,
    get_claim_classification,
    get_document_verdicts as get_document_verdicts_service,
    submit_human_verdict as submit_human_verdict_service,
)

claim_router = APIRouter(tags=["verdict-classification"])
document_router = APIRouter(prefix="/documents", tags=["verdict-classification"])


@claim_router.post(
    "/claims/{claim_id}/classify-verdict",
    response_model=VerdictClassificationResponse,
)
def classify_one_verdict(
    claim_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return classify_claim(claim_id, current_user, db)


@claim_router.get(
    "/claims/{claim_id}/verdict",
    response_model=VerdictClassificationResponse,
)
def get_one_verdict(
    claim_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_claim_classification(claim_id, current_user, db)


@document_router.post(
    "/{document_id}/classify-verdicts",
)
def classify_document_verdicts(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return classify_document(document_id, current_user, db)


@document_router.get(
    "/{document_id}/verdicts",
)
def get_document_verdicts(
    document_id: UUID,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_document_verdicts_service(document_id, current_user, db, page, per_page)


@claim_router.post(
    "/claims/{claim_id}/human-verdict",
    response_model=HumanVerdictResponse,
)
def submit_human_verdict_endpoint(
    claim_id: UUID,
    payload: HumanVerdictRequest,
    reviewer: User = Depends(require_role(UserRole.REVIEWER, UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    return submit_human_verdict_service(
        claim_id,
        payload.verdict,
        payload.comment,
        payload.evidence_ids,
        reviewer,
        db,
    )
