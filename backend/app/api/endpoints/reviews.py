"""Human review workflow API endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_role
from app.database.session import get_db
from app.models.enums import ReviewStatus, UserRole, Verdict
from app.models.user import User
from app.schemas.reviews import (
    ReviewDetailResponse,
    ReviewHistoryResponse,
    ReviewInvestigationRequest,
    ReviewQueueResponse,
    ReviewSubmitRequest,
)
from app.services.human_review.human_review_service import (
    get_review_detail,
    get_review_history,
    get_review_queue,
    list_document_reviews,
    request_investigation,
    submit_human_review,
)

router = APIRouter(prefix="/reviews", tags=["human-review"])
document_router = APIRouter(prefix="/documents", tags=["human-review"])


@router.get(
    "/queue",
    response_model=ReviewQueueResponse,
)
def review_queue(
    document_id: UUID | None = Query(default=None),
    verdict: Verdict | None = Query(default=None),
    review_status: ReviewStatus | None = Query(default=None),
    min_confidence: float | None = Query(default=None, ge=0.0, le=1.0),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    reviewer: User = Depends(require_role(UserRole.REVIEWER, UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    return get_review_queue(
        reviewer,
        db,
        document_id=document_id,
        verdict=verdict,
        review_status=review_status,
        min_confidence=min_confidence,
        page=page,
        per_page=per_page,
    )


@router.get(
    "/{review_id}",
    response_model=ReviewDetailResponse,
)
def review_detail(
    review_id: UUID,
    reviewer: User = Depends(require_role(UserRole.REVIEWER, UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    return get_review_detail(review_id, reviewer, db)


@router.post(
    "/{review_id}/submit",
)
def submit_review(
    review_id: UUID,
    payload: ReviewSubmitRequest,
    reviewer: User = Depends(require_role(UserRole.REVIEWER, UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    return submit_human_review(
        review_id,
        payload.verdict,
        payload.explanation,
        payload.notes,
        payload.evidence_ids,
        reviewer,
        db,
    )


@router.post(
    "/{review_id}/request-investigation",
)
def request_review_investigation(
    review_id: UUID,
    payload: ReviewInvestigationRequest,
    reviewer: User = Depends(require_role(UserRole.REVIEWER, UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    return request_investigation(
        review_id,
        payload.explanation,
        payload.notes,
        payload.evidence_ids,
        reviewer,
        db,
    )


@router.get(
    "/{review_id}/history",
    response_model=ReviewHistoryResponse,
)
def review_history(
    review_id: UUID,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    reviewer: User = Depends(require_role(UserRole.REVIEWER, UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    return get_review_history(review_id, reviewer, db, page, per_page)


@document_router.get(
    "/{document_id}/reviews",
)
def document_reviews(
    document_id: UUID,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    reviewer: User = Depends(require_role(UserRole.REVIEWER, UserRole.ADMIN)),
    db: Session = Depends(get_db),
):
    return list_document_reviews(document_id, reviewer, db, page, per_page)
