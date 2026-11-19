"""Evidence-grounded AI claim verification service for Phase 10."""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from uuid import UUID

import httpx
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import verify_resource_ownership
from app.core.config import get_settings
from app.models.document import Claim, ClaimCitation, Citation, Document
from app.models.enums import (
    ConfidenceLabel,
    EvidenceRelation,
    Verdict,
    VerificationStatus,
)
from app.models.research import EvidencePassage, ResearchSource
from app.models.user import User
from app.models.verification import VerificationEvidence, VerificationResult
from app.schemas.verification import GeminiVerificationOutput

logger = logging.getLogger(__name__)
PROMPT_VERSION = "phase10-v1"

VERIFICATION_PROMPT_TEMPLATE = """You are an evidence-based academic claim verification engine.

Evaluate the supplied academic claim strictly against the supplied research evidence.
Do not rely on unsupported general knowledge.
Do not invent citations, publications, DOIs, quotations or evidence.
Do not treat semantic similarity as proof of support.
Distinguish direct evidence from indirect evidence.
Distinguish correlation from causation.
Check whether numerical values, units, population, context and conditions match.
Identify contradictions and limitations.
If evidence is missing, inaccessible, ambiguous or insufficient, explicitly report that verification cannot be completed reliably.
Never force a positive or negative conclusion when evidence is insufficient.
Every important conclusion must reference the supplied evidence IDs.

Distinguish direct support, partial support, no demonstrated support, direct contradiction,
potentially outdated findings, and insufficient or ambiguous evidence.

Return JSON only. Evidence IDs must come exclusively from the supplied evidence set.
Allowed verdict values: supported, partly_supported, unsupported, contradictory,
possibly_outdated, needs_review.

Claim:
{claim}

Claim location:
{location}

Claim category:
{claim_category}

Citation markers:
{citation_markers}

Matched references:
{references}

Supplied evidence:
{evidence}
"""


def _owned_document(document_id: UUID, current_user: User, db: Session) -> Document:
    doc = db.execute(select(Document).where(Document.id == document_id)).scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    verify_resource_ownership(doc.user_id, current_user)
    return doc


def confidence_label(score: float) -> ConfidenceLabel:
    if score >= 0.75:
        return ConfidenceLabel.HIGH
    if score >= 0.45:
        return ConfidenceLabel.MEDIUM
    return ConfidenceLabel.LOW


def _claim_evidence(claim: Claim, db: Session) -> list[EvidencePassage]:
    source_ids: list[UUID] = []
    links = list(db.execute(
        select(ClaimCitation).where(ClaimCitation.claim_id == claim.id)
    ).scalars().all())
    for link in links:
        citation = db.get(Citation, link.citation_id)
        if citation and citation.research_source_id:
            source_ids.append(citation.research_source_id)
    source_ids = list(dict.fromkeys(source_ids))
    if source_ids:
        evidence = list(db.execute(
            select(EvidencePassage)
            .where(EvidencePassage.source_id.in_(source_ids))
            .order_by(EvidencePassage.relevance_score.desc().nullslast(), EvidencePassage.created_at)
        ).scalars().all())
        if evidence:
            return evidence

    evidence = list(db.execute(
        select(EvidencePassage)
        .where(EvidencePassage.claim_id == claim.id)
        .order_by(EvidencePassage.relevance_score.desc().nullslast(), EvidencePassage.created_at)
    ).scalars().all())
    return evidence


def _references(claim: Claim, db: Session) -> list[dict]:
    references: list[dict] = []
    links = list(db.execute(
        select(ClaimCitation).where(ClaimCitation.claim_id == claim.id)
    ).scalars().all())
    for link in links:
        citation = db.get(Citation, link.citation_id)
        if not citation:
            continue
        source = db.get(ResearchSource, citation.research_source_id) if citation.research_source_id else None
        references.append({
            "citation_marker": citation.original_marker or citation.citation_text,
            "mapping_status": getattr(link, "mapping_status", None).value if getattr(link, "mapping_status", None) else None,
            "reference_text": citation.citation_text,
            "doi": source.doi if source else citation.doi,
            "title": source.title if source else citation.publication_title,
            "publication_year": source.publication_year if source else citation.publication_year,
            "source_url": source.source_url if source else citation.url,
        })
    return references


def _gemini_verify(claim: Claim, evidence: list[EvidencePassage], references: list[dict], db: Session) -> GeminiVerificationOutput:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise RuntimeError("Gemini API key is not configured")

    evidence_payload = [
        {
            "evidence_id": str(item.id),
            "source_id": str(item.source_id),
            "publication_title": (
                db.get(ResearchSource, item.source_id).title
                if db.get(ResearchSource, item.source_id)
                else "Unknown source"
            ),
            "content_type": item.content_type.value,
            "section_name": item.section_name,
            "page_number": item.page_number,
            "paragraph_number": item.paragraph_number,
            "doi": item.doi,
            "source_url": item.source_url,
            "text": item.passage_text,
        }
        for item in evidence
    ]
    prompt = VERIFICATION_PROMPT_TEMPLATE.format(
        claim=claim.normalized_text or claim.original_text,
        location={
            "page_number": claim.page_number,
            "paragraph_index": claim.paragraph_number,
            "section_heading": claim.section_heading,
        },
        claim_category=claim.claim_type.value,
        citation_markers=claim.citation_markers,
        references=references,
        evidence=evidence_payload,
    )
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.gemini_model}:generateContent"
    )
    headers = {"x-goog-api-key": settings.gemini_api_key.get_secret_value()}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"},
    }
    last_error: Exception | None = None
    for attempt in range(settings.gemini_max_retries + 1):
        try:
            response = httpx.post(
                url,
                headers=headers,
                json=payload,
                timeout=settings.gemini_timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
                text = re.sub(r"\s*```$", "", text)
            parsed = GeminiVerificationOutput.model_validate_json(text)
            valid_ids = {str(item.id) for item in evidence}
            if any(str(item) not in valid_ids for item in parsed.supporting_evidence_ids):
                raise ValueError("Supporting evidence ID is not in the supplied evidence set")
            if any(str(item) not in valid_ids for item in parsed.contradicting_evidence_ids):
                raise ValueError("Contradicting evidence ID is not in the supplied evidence set")
            return parsed
        except (httpx.HTTPStatusError, httpx.TimeoutException, KeyError, ValidationError, ValueError) as exc:
            last_error = exc
            if attempt < settings.gemini_max_retries:
                time.sleep(0.25 * (attempt + 1))
        except Exception as exc:
            last_error = exc
            if attempt < settings.gemini_max_retries:
                time.sleep(0.25 * (attempt + 1))
    raise RuntimeError("Gemini verification unavailable") from last_error


def _add_verification_evidence(
    verification: VerificationResult,
    output: GeminiVerificationOutput,
    evidence: list[EvidencePassage],
    db: Session,
) -> None:
    evidence_by_id = {str(item.id): item for item in evidence}
    supporting = {str(item) for item in output.supporting_evidence_ids}
    contradicting = {str(item) for item in output.contradicting_evidence_ids}
    for evidence_id, passage in evidence_by_id.items():
        if evidence_id not in supporting and evidence_id not in contradicting:
            continue
        relation = (
            EvidenceRelation.SUPPORTING
            if evidence_id in supporting
            else EvidenceRelation.CONTRADICTING
        )
        existing = db.execute(
            select(VerificationEvidence).where(
                VerificationEvidence.verification_result_id == verification.id,
                VerificationEvidence.evidence_passage_id == passage.id,
            )
        ).scalar_one_or_none()
        if existing is None:
            db.add(VerificationEvidence(
                verification_result_id=verification.id,
                evidence_passage_id=passage.id,
                relation=relation,
                relevance_score=max(0.0, min(1.0, passage.relevance_score or 0.0)),
                rationale=(
                    "Gemini classified this passage as supporting evidence"
                    if relation == EvidenceRelation.SUPPORTING
                    else "Gemini classified this passage as contradicting evidence"
                ),
            ))


def verify_claim(
    claim_id: UUID,
    current_user: User,
    db: Session,
) -> VerificationResult:
    claim = db.get(Claim, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    doc = db.get(Document, claim.document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    verify_resource_ownership(doc.user_id, current_user)
    if not (claim.normalized_text or claim.original_text or "").strip():
        raise HTTPException(status_code=422, detail="Claim text is empty")

    settings = get_settings()
    latest = db.execute(
        select(VerificationResult)
        .where(
            VerificationResult.claim_id == claim.id,
            VerificationResult.prompt_version == PROMPT_VERSION,
            VerificationResult.model_name == settings.gemini_model,
        )
        .order_by(VerificationResult.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if latest is not None and latest.verification_status in (
        VerificationStatus.COMPLETED,
        VerificationStatus.NEEDS_REVIEW,
    ):
        return latest

    evidence = _claim_evidence(claim, db)
    references = _references(claim, db)
    if not evidence:
        result = VerificationResult(
            claim_id=claim.id,
            document_version_id=claim.document_version_id,
            verdict=Verdict.NEEDS_REVIEW,
            explanation="Insufficient evidence: no usable Phase 9 evidence passages were available.",
            confidence=ConfidenceLabel.LOW,
            confidence_score=0.0,
            verification_status=VerificationStatus.NEEDS_REVIEW,
            structured_analysis={
                "semantic_alignment": "Not assessable",
                "context_match": "Not assessable",
                "numerical_consistency": "Not assessable",
                "causal_consistency": "Not assessable",
                "scope_assessment": "Not assessable",
                "temporal_assessment": "Not assessable",
            },
            supporting_evidence_ids=[],
            contradicting_evidence_ids=[],
            limitations=["No usable evidence passages were retrieved."],
            unresolved_questions=["Obtain accessible research evidence before verification."],
            model_provider="gemini",
            model_name=settings.gemini_model,
            prompt_version=PROMPT_VERSION,
            requires_human_review=True,
            verified_at=datetime.now(timezone.utc),
        )
        db.add(result)
        db.commit()
        db.refresh(result)
        return result

    try:
        output = _gemini_verify(claim, evidence, references, db)
        result = VerificationResult(
            claim_id=claim.id,
            document_version_id=claim.document_version_id,
            verdict=output.verdict,
            explanation=output.reasoning_summary,
            confidence=confidence_label(output.confidence),
            confidence_score=output.confidence,
            verification_status=VerificationStatus.COMPLETED,
            structured_analysis={
                "semantic_alignment": output.semantic_alignment,
                "context_match": output.context_match,
                "numerical_consistency": output.numerical_consistency,
                "causal_consistency": output.causal_consistency,
                "scope_assessment": output.scope_assessment,
                "temporal_assessment": output.temporal_assessment,
            },
            supporting_evidence_ids=[str(item) for item in output.supporting_evidence_ids],
            contradicting_evidence_ids=[str(item) for item in output.contradicting_evidence_ids],
            limitations=output.limitations,
            unresolved_questions=output.unresolved_questions,
            model_provider="gemini",
            model_name=settings.gemini_model,
            prompt_version=PROMPT_VERSION,
            requires_human_review=output.requires_human_review,
            verified_at=datetime.now(timezone.utc),
        )
        db.add(result)
        db.flush()
        _add_verification_evidence(result, output, evidence, db)
        db.commit()
        db.refresh(result)
        return result
    except Exception as exc:
        db.rollback()
        logger.warning("Gemini verification failed: %s", type(exc).__name__)
        result = VerificationResult(
            claim_id=claim.id,
            document_version_id=claim.document_version_id,
            verdict=Verdict.NEEDS_REVIEW,
            explanation="Verification could not be completed because the AI verification service failed.",
            confidence=ConfidenceLabel.LOW,
            confidence_score=0.0,
            verification_status=VerificationStatus.FAILED,
            structured_analysis={},
            supporting_evidence_ids=[],
            contradicting_evidence_ids=[],
            limitations=["The Gemini verification response was unavailable or invalid."],
            unresolved_questions=["Retry verification after provider recovery."],
            model_provider="gemini",
            model_name=settings.gemini_model,
            prompt_version=PROMPT_VERSION,
            requires_human_review=True,
            error_message="Gemini verification unavailable",
            verified_at=datetime.now(timezone.utc),
        )
        db.add(result)
        db.commit()
        db.refresh(result)
        return result


def get_claim_verification(
    claim_id: UUID,
    current_user: User,
    db: Session,
) -> VerificationResult:
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
    return result


def get_verification_history(
    claim_id: UUID,
    current_user: User,
    db: Session,
    page: int = 1,
    per_page: int = 20,
) -> dict:
    claim = db.get(Claim, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    doc = db.get(Document, claim.document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    verify_resource_ownership(doc.user_id, current_user)
    statement = select(VerificationResult).where(
        VerificationResult.claim_id == claim_id
    )
    all_results = list(db.execute(
        statement.order_by(VerificationResult.created_at.desc())
    ).scalars().all())
    offset = (page - 1) * per_page
    return {
        "claim_id": claim_id,
        "verification_results": all_results[offset:offset + per_page],
        "pagination": {
            "total": len(all_results),
            "page": page,
            "per_page": per_page,
            "total_pages": (len(all_results) + per_page - 1) // per_page,
        },
    }


def verify_document(
    document_id: UUID,
    current_user: User,
    db: Session,
) -> dict:
    doc = _owned_document(document_id, current_user, db)
    from app.models.document import DocumentVersion

    latest_version = db.execute(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == doc.id)
        .order_by(DocumentVersion.version_number.desc())
        .limit(1)
    ).scalar_one_or_none()
    if latest_version is None:
        raise HTTPException(status_code=404, detail="Document has not been parsed yet")
    claims = list(db.execute(
        select(Claim)
        .where(Claim.document_version_id == latest_version.id)
        .order_by(Claim.created_at)
    ).scalars().all())
    results: list[VerificationResult] = []
    verified_count = 0
    failed_count = 0
    needs_review_count = 0
    for claim in claims:
        try:
            result = verify_claim(claim.id, current_user, db)
            results.append(result)
            if result.verification_status == VerificationStatus.COMPLETED:
                verified_count += 1
            elif result.verification_status == VerificationStatus.FAILED:
                failed_count += 1
            else:
                needs_review_count += 1
        except Exception as exc:
            db.rollback()
            logger.warning(
                "Document claim verification failed: claim=%s error=%s",
                claim.id,
                type(exc).__name__,
            )
            result = VerificationResult(
                claim_id=claim.id,
                document_version_id=latest_version.id,
                verdict=Verdict.NEEDS_REVIEW,
                explanation="This claim could not be verified safely.",
                confidence=ConfidenceLabel.LOW,
                confidence_score=0.0,
                verification_status=VerificationStatus.FAILED,
                structured_analysis={},
                supporting_evidence_ids=[],
                contradicting_evidence_ids=[],
                limitations=["Claim-level verification failed."],
                unresolved_questions=["Retry this claim verification."],
                model_provider="gemini",
                model_name=get_settings().gemini_model,
                prompt_version=PROMPT_VERSION,
                requires_human_review=True,
                error_message="Claim verification failed",
                verified_at=datetime.now(timezone.utc),
            )
            db.add(result)
            db.commit()
            db.refresh(result)
            results.append(result)
            failed_count += 1
    return {
        "document_id": doc.id,
        "version_id": latest_version.id,
        "total_claims": len(claims),
        "verified_count": verified_count,
        "failed_count": failed_count,
        "needs_review_count": needs_review_count,
        "results": results,
    }


def get_document_verification(
    document_id: UUID,
    current_user: User,
    db: Session,
    page: int = 1,
    per_page: int = 20,
) -> dict:
    doc = _owned_document(document_id, current_user, db)
    from app.models.document import DocumentVersion

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
    all_results: list[VerificationResult] = []
    if claim_ids:
        all_results = list(db.execute(
            select(VerificationResult)
            .where(VerificationResult.claim_id.in_(claim_ids))
            .order_by(VerificationResult.created_at.desc())
        ).scalars().all())
    offset = (page - 1) * per_page
    return {
        "document_id": doc.id,
        "version_id": version.id,
        "total_claims": len(claim_ids),
        "verified_count": sum(
            1 for item in all_results
            if item.verification_status == VerificationStatus.COMPLETED
        ),
        "failed_count": sum(
            1 for item in all_results
            if item.verification_status == VerificationStatus.FAILED
        ),
        "needs_review_count": sum(
            1 for item in all_results
            if item.verification_status == VerificationStatus.NEEDS_REVIEW
        ),
        "results": all_results[offset:offset + per_page],
    }
