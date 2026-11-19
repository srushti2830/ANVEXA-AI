"""Deterministic final-verdict classification based only on Phase 10 output."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import verify_resource_ownership
from app.models.document import Claim, Document, DocumentVersion
from app.models.enums import ReviewAction, Verdict, VerificationStatus
from app.models.user import User
from app.models.verification import (
    ReviewHistory,
    VerificationEvidence,
    VerificationResult,
)


def _owned_document(document_id: UUID, current_user: User, db: Session) -> Document:
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    verify_resource_ownership(doc.user_id, current_user)
    return doc


def classify_verification_result(result: VerificationResult) -> tuple[Verdict, str, float]:
    if result.verification_status != VerificationStatus.COMPLETED:
        return (
            Verdict.NEEDS_REVIEW,
            "The Phase 10 verification was failed or incomplete, so no final verdict can be established.",
            0.0,
        )

    supporting = set(result.supporting_evidence_ids)
    contradicting = set(result.contradicting_evidence_ids)
    limitations = " ".join(result.limitations).lower()
    unresolved = " ".join(result.unresolved_questions).lower()
    analysis = " ".join(str(value) for value in result.structured_analysis.values()).lower()
    explanation = (result.explanation or "").lower()
    combined = " ".join([limitations, unresolved, analysis, explanation])

    if contradicting:
        return (
            Verdict.CONTRADICTORY,
            "One or more supplied evidence passages are classified as contradicting the claim.",
            0.90,
        )

    temporal_markers = (
        "outdated",
        "newer evidence",
        "temporal",
        "publication date",
        "no longer current",
        "potentially outdated",
    )
    if result.verdict == Verdict.POSSIBLY_OUTDATED or any(marker in combined for marker in temporal_markers):
        return (
            Verdict.POSSIBLY_OUTDATED,
            "The Phase 10 analysis identifies temporal relevance or potentially outdated findings.",
            0.65,
        )

    if result.requires_human_review or not supporting:
        if result.requires_human_review:
            reason = "Human review is required by the Phase 10 analysis."
        else:
            reason = "No supporting evidence ID was validated for this claim."
        return (Verdict.NEEDS_REVIEW, reason, 0.20)

    partial_markers = (
        "partial",
        "limited",
        "broader",
        "mismatch",
        "not establish",
        "indirect",
        "insufficient",
        "ambiguous",
        "correlation",
    )
    if (
        result.verdict in (Verdict.PARTLY_SUPPORTED, Verdict.UNSUPPORTED)
        or any(marker in combined for marker in partial_markers)
    ):
        final_verdict = (
            Verdict.UNSUPPORTED
            if result.verdict == Verdict.UNSUPPORTED
            else Verdict.PARTLY_SUPPORTED
        )
        reason = (
            "Evidence exists, but the Phase 10 analysis indicates incomplete or limited support."
            if final_verdict == Verdict.PARTLY_SUPPORTED
            else "The Phase 10 analysis found no demonstrated support for the claim."
        )
        return (final_verdict, reason, 0.55)

    if result.verdict == Verdict.SUPPORTED and supporting:
        return (
            Verdict.SUPPORTED,
            "The Phase 10 result and its preserved supporting evidence indicate direct support.",
            max(0.0, min(1.0, result.confidence_score or 0.75)),
        )

    return (
        Verdict.NEEDS_REVIEW,
        "The available Phase 10 evidence and analysis do not map unambiguously to a final category.",
        0.25,
    )


def classify_claim(
    claim_id: UUID,
    current_user: User,
    db: Session,
) -> dict:
    claim = db.get(Claim, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    doc = db.get(Document, claim.document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    verify_resource_ownership(doc.user_id, current_user)

    result = db.execute(
        select(VerificationResult)
        .where(VerificationResult.claim_id == claim_id)
        .order_by(VerificationResult.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if result is None:
        raise HTTPException(status_code=404, detail="Verification result not found")

    if result.final_verdict is not None:
        return _classification_response(result)

    final_verdict, reason, confidence = classify_verification_result(result)
    result.final_verdict = final_verdict
    result.classification_method = "phase11-rule-v1"
    result.classification_reason = reason
    result.classification_confidence = confidence
    result.classified_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(result)
    return _classification_response(result)


def get_claim_classification(
    claim_id: UUID,
    current_user: User,
    db: Session,
) -> dict:
    claim = db.get(Claim, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    doc = db.get(Document, claim.document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    verify_resource_ownership(doc.user_id, current_user)
    result = db.execute(
        select(VerificationResult)
        .where(VerificationResult.claim_id == claim_id)
        .order_by(VerificationResult.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if result is None or result.final_verdict is None:
        raise HTTPException(status_code=404, detail="Verdict classification not found")
    return _classification_response(result)


def classify_document(
    document_id: UUID,
    current_user: User,
    db: Session,
) -> dict:
    doc = _owned_document(document_id, current_user, db)
    version = db.execute(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == doc.id)
        .order_by(DocumentVersion.version_number.desc())
        .limit(1)
    ).scalar_one_or_none()
    if version is None:
        raise HTTPException(status_code=404, detail="Document has not been parsed yet")
    claims = list(db.execute(
        select(Claim)
        .where(Claim.document_version_id == version.id)
        .order_by(Claim.created_at)
    ).scalars().all())
    classifications = []
    counts = {verdict: 0 for verdict in Verdict}
    failed = 0
    for claim in claims:
        try:
            classification = classify_claim(claim.id, current_user, db)
            classifications.append(classification)
            counts[classification["final_verdict"]] += 1
        except HTTPException as exc:
            if exc.status_code == 404:
                failed += 1
            else:
                raise
    return {
        "document_id": doc.id,
        "version_id": version.id,
        "total_claims": len(claims),
        "classified_count": len(classifications),
        "failed_count": failed,
        "counts": {key.value: value for key, value in counts.items()},
        "classifications": classifications,
    }


def get_document_verdicts(
    document_id: UUID,
    current_user: User,
    db: Session,
    page: int = 1,
    per_page: int = 20,
) -> dict:
    doc = _owned_document(document_id, current_user, db)
    version = db.execute(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == doc.id)
        .order_by(DocumentVersion.version_number.desc())
        .limit(1)
    ).scalar_one_or_none()
    if version is None:
        raise HTTPException(status_code=404, detail="Document has not been parsed yet")
    claim_ids = list(db.execute(
        select(Claim.id).where(Claim.document_version_id == version.id)
    ).scalars().all())
    results = list(db.execute(
        select(VerificationResult)
        .where(
            VerificationResult.claim_id.in_(claim_ids),
            VerificationResult.final_verdict.is_not(None),
        )
        .order_by(VerificationResult.created_at.desc())
    ).scalars().all()) if claim_ids else []
    offset = (page - 1) * per_page
    classifications = [_classification_response(item) for item in results]
    return {
        "document_id": doc.id,
        "version_id": version.id,
        "total_claims": len(claim_ids),
        "classifications": classifications[offset:offset + per_page],
        "pagination": {
            "total": len(classifications),
            "page": page,
            "per_page": per_page,
            "total_pages": (len(classifications) + per_page - 1) // per_page,
        },
    }


def submit_human_verdict(
    claim_id: UUID,
    verdict: Verdict,
    comment: str,
    evidence_ids: list[UUID],
    reviewer: User,
    db: Session,
) -> dict:
    claim = db.get(Claim, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    doc = db.get(Document, claim.document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    result = db.execute(
        select(VerificationResult)
        .where(VerificationResult.claim_id == claim_id)
        .order_by(VerificationResult.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if result is None:
        raise HTTPException(status_code=404, detail="Verification result not found")

    valid_evidence_ids = {
        str(item) for item in result.supporting_evidence_ids + result.contradicting_evidence_ids
    }
    for evidence_id in evidence_ids:
        if str(evidence_id) not in valid_evidence_ids:
            raise HTTPException(
                status_code=422,
                detail="Human review evidence ID is not part of this verification",
            )

    original_ai_verdict = result.final_verdict or result.verdict
    review = ReviewHistory(
        verification_result_id=result.id,
        reviewer_id=reviewer.id,
        action=ReviewAction.CHANGE_VERDICT,
        original_ai_verdict=original_ai_verdict,
        human_verdict=verdict,
        reviewer_comment=comment,
        is_resolved=True,
        reviewed_at=datetime.now(timezone.utc),
    )
    db.add(review)
    db.flush()
    for evidence_id in evidence_ids:
        evidence = db.get(
            __import__("app.models.research", fromlist=["EvidencePassage"]).EvidencePassage,
            evidence_id,
        )
        if evidence is not None:
            review.additional_evidence.append(evidence)
    result.final_verdict = verdict
    result.classification_method = "human-review"
    result.classification_reason = comment
    result.classification_confidence = 1.0
    result.classified_at = datetime.now(timezone.utc)
    result.requires_human_review = False
    db.commit()
    db.refresh(review)
    return {
        "review_id": review.id,
        "verification_result_id": result.id,
        "claim_id": claim_id,
        "original_ai_verdict": original_ai_verdict,
        "human_verdict": verdict,
        "comment": comment,
        "is_resolved": True,
        "reviewed_at": review.reviewed_at,
    }


def _classification_response(result: VerificationResult) -> dict:
    return {
        "verification_result_id": result.id,
        "claim_id": result.claim_id,
        "ai_verdict": result.verdict,
        "final_verdict": result.final_verdict,
        "classification_method": result.classification_method or "unclassified",
        "classification_reason": result.classification_reason or "No classification reason recorded.",
        "classification_confidence": result.classification_confidence or 0.0,
        "supporting_evidence_ids": result.supporting_evidence_ids,
        "contradicting_evidence_ids": result.contradicting_evidence_ids,
        "limitations": result.limitations,
        "unresolved_questions": result.unresolved_questions,
        "requires_human_review": result.requires_human_review,
        "classified_at": result.classified_at or result.updated_at,
    }
