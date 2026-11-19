"""Human review queue and review-history workflow."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import verify_resource_ownership
from app.models.document import Claim, Document, DocumentVersion
from app.models.enums import (
    ReviewAction,
    ReviewStatus,
    UserRole,
    Verdict,
)
from app.models.research import EvidencePassage, ResearchSource
from app.models.user import User
from app.models.verification import (
    ReviewHistory,
    VerificationEvidence,
    VerificationResult,
)


def _ensure_reviewer(reviewer: User) -> None:
    from app.models.enums import UserRole

    if reviewer.role not in (UserRole.REVIEWER, UserRole.ADMIN):
        raise HTTPException(status_code=403, detail="Reviewer permission required")


def _get_review_result(review_id: UUID, db: Session) -> VerificationResult:
    result = db.get(VerificationResult, review_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Review not found")
    return result


def _claim_document(result: VerificationResult, db: Session) -> tuple[Claim, Document]:
    claim = db.get(Claim, result.claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    document = db.get(Document, claim.document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return claim, document


def _evidence_payload(
    result: VerificationResult,
    relation: str,
    db: Session,
) -> list[dict]:
    evidence_ids = (
        result.supporting_evidence_ids
        if relation == "supporting"
        else result.contradicting_evidence_ids
    )
    output: list[dict] = []
    for evidence_id in evidence_ids:
        try:
            evidence_uuid = UUID(str(evidence_id))
        except (ValueError, TypeError):
            continue
        passage = db.get(EvidencePassage, evidence_uuid)
        if passage is None:
            continue
        source = db.get(ResearchSource, passage.source_id)
        evidence_relation = (
            db.execute(
                select(VerificationEvidence).where(
                    VerificationEvidence.verification_result_id == result.id,
                    VerificationEvidence.evidence_passage_id == passage.id,
                )
            ).scalar_one_or_none()
        )
        output.append({
            "evidence_id": passage.id,
            "source_id": passage.source_id,
            "publication_title": source.title if source else "Unknown source",
            "evidence_text": passage.passage_text,
            "content_type": passage.content_type.value,
            "section_name": passage.section_name,
            "page_number": passage.page_number,
            "paragraph_number": passage.paragraph_number,
            "source_url": passage.source_url or (source.source_url if source else None),
            "doi": passage.doi or (source.doi if source else None),
            "publication_year": source.publication_year if source else None,
            "relation": evidence_relation.relation.value if evidence_relation else relation,
        })
    return output


def get_review_queue(
    reviewer: User,
    db: Session,
    *,
    document_id: UUID | None = None,
    verdict: Verdict | None = None,
    review_status: ReviewStatus | None = None,
    min_confidence: float | None = None,
    page: int = 1,
    per_page: int = 20,
) -> dict:
    _ensure_reviewer(reviewer)
    statement = select(VerificationResult)
    if document_id is not None:
        claim_ids = list(db.execute(
            select(Claim.id).where(
                Claim.document_id == document_id
            )
        ).scalars().all())
        if not claim_ids:
            statement = statement.where(VerificationResult.claim_id.in_([]))
        else:
            document = db.get(Document, document_id)
            if document is None:
                raise HTTPException(status_code=404, detail="Document not found")
            verify_resource_ownership(
                document.user_id,
                reviewer,
                allow_roles=(UserRole.REVIEWER, UserRole.ADMIN),
            )
            statement = statement.where(VerificationResult.claim_id.in_(claim_ids))
    if review_status is not None:
        statement = statement.where(VerificationResult.review_status == review_status)
    else:
        statement = statement.where(
            VerificationResult.review_status.in_([
                ReviewStatus.PENDING,
                ReviewStatus.IN_REVIEW,
                ReviewStatus.INVESTIGATION_REQUESTED,
            ])
        )
    if min_confidence is not None:
        statement = statement.where(
            VerificationResult.confidence_score.is_not(None),
            VerificationResult.confidence_score >= min_confidence,
        )

    all_results = list(db.execute(
        statement.order_by(VerificationResult.created_at.desc())
    ).scalars().all())
    items = []
    for result in all_results:
        claim, document = _claim_document(result, db)
        if not (
            result.requires_human_review
            or result.final_verdict == Verdict.NEEDS_REVIEW
            or result.verdict == Verdict.NEEDS_REVIEW
            or result.review_status == ReviewStatus.INVESTIGATION_REQUESTED
        ):
            continue
        ai_verdict = result.final_verdict or result.verdict
        if verdict is not None and ai_verdict != verdict:
            continue
        items.append({
            "review_id": result.id,
            "verification_result_id": result.id,
            "claim_id": result.claim_id,
            "document_id": document.id,
            "document_title": document.title,
            "claim_text": claim.normalized_text or claim.original_text,
            "ai_verdict": ai_verdict,
            "final_verdict": result.final_verdict,
            "confidence": result.confidence_score,
            "confidence_label": result.confidence.value if result.confidence else None,
            "review_status": result.review_status,
            "requires_human_review": result.requires_human_review,
            "created_at": result.created_at,
        })
    offset = (page - 1) * per_page
    paged = items[offset:offset + per_page]
    return {
        "reviews": paged,
        "pagination": {
            "total": len(items),
            "page": page,
            "per_page": per_page,
            "total_pages": (len(items) + per_page - 1) // per_page,
        },
    }


def get_review_detail(
    review_id: UUID,
    reviewer: User,
    db: Session,
) -> dict:
    _ensure_reviewer(reviewer)
    result = _get_review_result(review_id, db)
    claim, document = _claim_document(result, db)
    verify_resource_ownership(
        document.user_id,
        reviewer,
        allow_roles=(UserRole.REVIEWER, UserRole.ADMIN),
    )
    return {
        "review_id": result.id,
        "verification_result_id": result.id,
        "claim_id": result.claim_id,
        "document_id": document.id,
        "document_title": document.title,
        "filename": document.filename,
        "claim_text": claim.normalized_text or claim.original_text,
        "claim_category": claim.claim_type.value,
        "page_number": claim.page_number,
        "paragraph_index": claim.paragraph_number,
        "section_heading": claim.section_heading,
        "ai_verdict": result.final_verdict or result.verdict,
        "final_verdict": result.final_verdict,
        "ai_explanation": result.explanation,
        "confidence": result.confidence_score,
        "confidence_label": result.confidence.value if result.confidence else None,
        "requires_human_review": result.requires_human_review,
        "review_status": result.review_status,
        "assigned_reviewer_id": result.assigned_reviewer_id,
        "supporting_evidence": _evidence_payload(result, "supporting", db),
        "contradicting_evidence": _evidence_payload(result, "contradicting", db),
        "limitations": result.limitations,
        "unresolved_questions": result.unresolved_questions,
        "structured_analysis": result.structured_analysis,
        "created_at": result.created_at,
    }


def submit_human_review(
    review_id: UUID,
    verdict: Verdict,
    explanation: str,
    notes: str | None,
    evidence_ids: list[UUID],
    reviewer: User,
    db: Session,
) -> dict:
    _ensure_reviewer(reviewer)
    result = _get_review_result(review_id, db)
    claim, document = _claim_document(result, db)
    verify_resource_ownership(document.user_id, reviewer)

    if result.review_status == ReviewStatus.RESOLVED:
        existing = db.execute(
            select(ReviewHistory)
            .where(
                ReviewHistory.verification_result_id == result.id,
                ReviewHistory.action == ReviewAction.CHANGE_VERDICT,
            )
            .order_by(ReviewHistory.reviewed_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if existing is not None:
            return _history_response_item(existing)

    if verdict not in Verdict:
        raise HTTPException(status_code=422, detail="Invalid human verdict")
    if not explanation or len(explanation.strip()) < 10:
        raise HTTPException(status_code=422, detail="Reviewer explanation is required")

    valid_evidence_ids = {
        str(item)
        for item in result.supporting_evidence_ids + result.contradicting_evidence_ids
    }
    for evidence_id in evidence_ids:
        if str(evidence_id) not in valid_evidence_ids:
            raise HTTPException(
                status_code=422,
                detail="Evidence ID is not part of this verification",
            )

    original_ai_verdict = result.final_verdict or result.verdict
    full_comment = explanation.strip()
    if notes and notes.strip():
        full_comment = f"{full_comment}\n\nReviewer notes:\n{notes.strip()}"

    review = ReviewHistory(
        verification_result_id=result.id,
        reviewer_id=reviewer.id,
        action=ReviewAction.CHANGE_VERDICT,
        original_ai_verdict=original_ai_verdict,
        human_verdict=verdict,
        reviewer_comment=full_comment,
        is_resolved=True,
        reviewed_at=datetime.now(timezone.utc),
    )
    db.add(review)
    db.flush()
    for evidence_id in evidence_ids:
        passage = db.get(EvidencePassage, evidence_id)
        if passage is not None:
            review.additional_evidence.append(passage)

    result.final_verdict = verdict
    result.verdict = verdict if result.verdict == Verdict.NEEDS_REVIEW else result.verdict
    result.classification_method = "human-review"
    result.classification_reason = full_comment
    result.classification_confidence = 1.0
    result.classified_at = datetime.now(timezone.utc)
    result.requires_human_review = False
    result.review_status = ReviewStatus.RESOLVED
    result.assigned_reviewer_id = reviewer.id
    db.commit()
    db.refresh(review)
    return _history_response_item(review)


def request_investigation(
    review_id: UUID,
    explanation: str,
    notes: str | None,
    evidence_ids: list[UUID],
    reviewer: User,
    db: Session,
) -> dict:
    _ensure_reviewer(reviewer)
    result = _get_review_result(review_id, db)
    claim, document = _claim_document(result, db)
    verify_resource_ownership(document.user_id, reviewer)
    if not explanation or len(explanation.strip()) < 10:
        raise HTTPException(status_code=422, detail="Investigation request explanation is required")
    if result.review_status == ReviewStatus.RESOLVED:
        raise HTTPException(status_code=409, detail="Resolved reviews cannot request investigation")

    valid_evidence_ids = {
        str(item)
        for item in result.supporting_evidence_ids + result.contradicting_evidence_ids
    }
    for evidence_id in evidence_ids:
        if str(evidence_id) not in valid_evidence_ids:
            raise HTTPException(status_code=422, detail="Evidence ID is not part of this verification")

    full_comment = explanation.strip()
    if notes and notes.strip():
        full_comment = f"{full_comment}\n\nInvestigation notes:\n{notes.strip()}"

    existing = db.execute(
        select(ReviewHistory)
        .where(
            ReviewHistory.verification_result_id == result.id,
            ReviewHistory.action == ReviewAction.REQUEST_INVESTIGATION,
        )
        .order_by(ReviewHistory.reviewed_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if existing is not None:
        return _history_response_item(existing)

    original_ai_verdict = result.final_verdict or result.verdict
    review = ReviewHistory(
        verification_result_id=result.id,
        reviewer_id=reviewer.id,
        action=ReviewAction.REQUEST_INVESTIGATION,
        original_ai_verdict=original_ai_verdict,
        human_verdict=Verdict.NEEDS_REVIEW,
        reviewer_comment=full_comment,
        is_resolved=False,
        reviewed_at=datetime.now(timezone.utc),
    )
    db.add(review)
    db.flush()
    for evidence_id in evidence_ids:
        passage = db.get(EvidencePassage, evidence_id)
        if passage is not None:
            review.additional_evidence.append(passage)
    result.review_status = ReviewStatus.INVESTIGATION_REQUESTED
    result.requires_human_review = True
    result.assigned_reviewer_id = reviewer.id
    result.review_requested_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(review)
    return _history_response_item(review)


def get_review_history(
    review_id: UUID,
    reviewer: User,
    db: Session,
    page: int = 1,
    per_page: int = 20,
) -> dict:
    _ensure_reviewer(reviewer)
    result = _get_review_result(review_id, db)
    claim, document = _claim_document(result, db)
    verify_resource_ownership(document.user_id, reviewer)
    all_history = list(db.execute(
        select(ReviewHistory)
        .where(ReviewHistory.verification_result_id == result.id)
        .order_by(ReviewHistory.reviewed_at.desc())
    ).scalars().all())
    offset = (page - 1) * per_page
    items = [_history_response_item(item) for item in all_history]
    return {
        "review_id": review_id,
        "history": items[offset:offset + per_page],
        "pagination": {
            "total": len(items),
            "page": page,
            "per_page": per_page,
            "total_pages": (len(items) + per_page - 1) // per_page,
        },
    }


def list_document_reviews(
    document_id: UUID,
    reviewer: User,
    db: Session,
    page: int = 1,
    per_page: int = 20,
) -> dict:
    _ensure_reviewer(reviewer)
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    verify_resource_ownership(document.user_id, reviewer)
    claim_ids = list(db.execute(
        select(Claim.id).where(Claim.document_id == document_id)
    ).scalars().all())
    results = list(db.execute(
        select(VerificationResult)
        .where(VerificationResult.claim_id.in_(claim_ids))
        .order_by(VerificationResult.created_at.desc())
    ).scalars().all()) if claim_ids else []
    items = []
    for result in results:
        claim = db.get(Claim, result.claim_id)
        if claim is None:
            continue
        items.append({
            "review_id": result.id,
            "verification_result_id": result.id,
            "claim_id": claim.id,
            "document_id": document.id,
            "document_title": document.title,
            "claim_text": claim.normalized_text or claim.original_text,
            "ai_verdict": result.final_verdict or result.verdict,
            "final_verdict": result.final_verdict,
            "confidence": result.confidence_score,
            "confidence_label": result.confidence.value if result.confidence else None,
            "review_status": result.review_status,
            "requires_human_review": result.requires_human_review,
            "created_at": result.created_at,
        })
    offset = (page - 1) * per_page
    return {
        "reviews": items[offset:offset + per_page],
        "pagination": {
            "total": len(items),
            "page": page,
            "per_page": per_page,
            "total_pages": (len(items) + per_page - 1) // per_page,
        },
    }


def _history_response_item(review: ReviewHistory) -> dict:
    return {
        "id": review.id,
        "verification_result_id": review.verification_result_id,
        "reviewer_id": review.reviewer_id,
        "action": review.action,
        "original_ai_verdict": review.original_ai_verdict,
        "human_verdict": review.human_verdict,
        "reviewer_comment": review.reviewer_comment,
        "is_resolved": review.is_resolved,
        "reviewed_at": review.reviewed_at,
    }
