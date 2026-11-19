"""Document reports and database-backed analytics for Phase 13."""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import verify_resource_ownership
from app.models.document import (
    Claim,
    ClaimCitation,
    Citation,
    Document,
    DocumentVersion,
)
from app.models.enums import (
    DocumentStatus,
    ReviewStatus,
    Verdict,
    VerificationStatus,
)
from app.models.research import EvidencePassage, ResearchSource
from app.models.user import User
from app.models.verification import (
    ReviewHistory,
    VerificationEvidence,
    VerificationResult,
)

SIX_VERDICTS = (
    "supported",
    "partly_supported",
    "unsupported",
    "contradictory",
    "possibly_outdated",
    "needs_review",
)


def _owned_document(document_id: UUID, current_user: User, db: Session) -> Document:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    verify_resource_ownership(document.user_id, current_user)
    return document


def _latest_version(document: Document, db: Session) -> DocumentVersion | None:
    return db.execute(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == document.id)
        .order_by(DocumentVersion.version_number.desc())
        .limit(1)
    ).scalar_one_or_none()


def _distribution(results: list[VerificationResult]) -> dict:
    counts = {verdict: 0 for verdict in SIX_VERDICTS}
    for result in results:
        verdict = result.final_verdict or result.verdict
        if verdict is not None:
            counts[verdict.value if hasattr(verdict, "value") else str(verdict)] += 1
    return counts


def _evidence_payload(
    result: VerificationResult,
    evidence_ids: list[str],
    relation: str,
    db: Session,
) -> list[dict]:
    output = []
    for evidence_id in evidence_ids:
        try:
            evidence_uuid = UUID(str(evidence_id))
        except (ValueError, TypeError):
            continue
        passage = db.get(EvidencePassage, evidence_uuid)
        if passage is None:
            continue
        source = db.get(ResearchSource, passage.source_id)
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
            "relation": relation,
        })
    return output


def _citation_payload(claim: Claim, db: Session) -> list[dict]:
    links = list(db.execute(
        select(ClaimCitation).where(ClaimCitation.claim_id == claim.id)
    ).scalars().all())
    output = []
    for link in links:
        citation = db.get(Citation, link.citation_id)
        if citation is None:
            continue
        output.append({
            "citation_id": citation.id,
            "citation_text": citation.citation_text,
            "original_marker": citation.original_marker,
            "normalized_marker": citation.normalized_marker,
            "style": citation.citation_type.value,
            "reference_number": citation.reference_number,
            "page_number": citation.page_number or link.page_number,
            "paragraph_number": citation.paragraph_number or link.paragraph_number,
        })
    return output


def _claim_report(claim: Claim, db: Session) -> dict:
    result = db.execute(
        select(VerificationResult)
        .where(VerificationResult.claim_id == claim.id)
        .order_by(VerificationResult.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    ai_verdict = result.verdict if result else None
    human_verdict = None
    result_label = "pending_review"
    final_verdict = None
    explanation = None
    confidence_label = None
    confidence_score = None
    limitations = []
    unresolved_questions = []
    review_status = "pending"
    supporting_evidence = []
    contradicting_evidence = []

    if result:
        final_verdict = result.final_verdict
        if result.reviews:
            human_review = sorted(
                result.reviews,
                key=lambda item: item.reviewed_at,
                reverse=True,
            )[0]
            human_verdict = human_review.human_verdict
        if result.final_verdict is not None:
            final_verdict = result.final_verdict
        if human_verdict is not None:
            result_label = "human_reviewed"
        elif ai_verdict is not None:
            result_label = "ai_generated"
        explanation = result.explanation
        confidence_label = result.confidence.value if result.confidence else None
        confidence_score = result.confidence_score
        limitations = result.limitations
        unresolved_questions = result.unresolved_questions
        review_status = result.review_status.value
        supporting_evidence = _evidence_payload(
            result,
            result.supporting_evidence_ids,
            "supporting",
            db,
        )
        contradicting_evidence = _evidence_payload(
            result,
            result.contradicting_evidence_ids,
            "contradicting",
            db,
        )

    history = []
    if result:
        history = [
            {
                "action": review.action.value,
                "original_ai_verdict": review.original_ai_verdict.value,
                "human_verdict": review.human_verdict.value,
                "reviewer_id": str(review.reviewer_id),
                "reviewer_comment": review.reviewer_comment,
                "is_resolved": review.is_resolved,
                "reviewed_at": review.reviewed_at.isoformat(),
            }
            for review in sorted(result.reviews, key=lambda item: item.reviewed_at)
        ]

    return {
        "claim_id": claim.id,
        "claim_text": claim.normalized_text or claim.original_text,
        "claim_category": claim.claim_type.value,
        "page_number": claim.page_number,
        "paragraph_index": claim.paragraph_number,
        "section_heading": claim.section_heading,
        "citation_markers": claim.citation_markers,
        "ai_verdict": ai_verdict,
        "human_verdict": human_verdict,
        "final_verdict": final_verdict,
        "result_label": result_label,
        "confidence_label": confidence_label,
        "confidence_score": confidence_score,
        "explanation": explanation,
        "limitations": limitations,
        "unresolved_questions": unresolved_questions,
        "supporting_evidence": supporting_evidence,
        "contradicting_evidence": contradicting_evidence,
        "citations": _citation_payload(claim, db),
        "review_status": review_status,
        "human_review_history": history,
    }


def build_document_report(
    document_id: UUID,
    current_user: User,
    db: Session,
) -> dict:
    document = _owned_document(document_id, current_user, db)
    version = _latest_version(document, db)
    claims = list(db.execute(
        select(Claim)
        .where(
            Claim.document_id == document.id,
            Claim.document_version_id == version.id if version else Claim.document_version_id.is_not(None),
        )
        .order_by(Claim.created_at)
    ).scalars().all()) if version else []

    claim_ids = [claim.id for claim in claims]
    results = list(db.execute(
        select(VerificationResult)
        .where(VerificationResult.claim_id.in_(claim_ids))
        .order_by(VerificationResult.created_at.desc())
    ).scalars().all()) if claim_ids else []

    distribution = _distribution(results)
    citations = list(db.execute(
        select(Citation)
        .where(Citation.document_version_id == version.id)
    ).scalars().all()) if version else []
    sources = list(db.execute(
        select(ResearchSource)
        .join(Citation, Citation.research_source_id == ResearchSource.id)
        .where(Citation.document_version_id == version.id)
        .distinct()
    ).scalars().all()) if version else []
    evidence_count = len(list(db.execute(
        select(EvidencePassage)
        .where(EvidencePassage.source_id.in_([source.id for source in sources]))
    ).scalars().all())) if sources else 0

    human_reviewed = sum(
        1 for claim in claims
        if db.execute(
            select(ReviewHistory)
            .join(VerificationResult, ReviewHistory.verification_result_id == VerificationResult.id)
            .where(
                VerificationResult.claim_id == claim.id,
                ReviewHistory.is_resolved.is_(True),
            )
            .limit(1)
        ).scalar_one_or_none() is not None
    )
    awaiting = sum(
        1 for result in results
        if result.requires_human_review
        or result.review_status in (
            ReviewStatus.PENDING,
            ReviewStatus.IN_REVIEW,
            ReviewStatus.INVESTIGATION_REQUESTED,
        )
    )
    unresolved = sum(
        1 for result in results
        if result.final_verdict == Verdict.NEEDS_REVIEW
        or result.review_status == ReviewStatus.INVESTIGATION_REQUESTED
    )

    recommendations = []
    if awaiting:
        recommendations.append("Route remaining claims marked for human review to authorized reviewers.")
    if unresolved:
        recommendations.append("Investigate unresolved claims and missing or contradictory evidence.")
    if not evidence_count:
        recommendations.append("No evidence passages were found; verification conclusions remain incomplete.")
    if not recommendations:
        recommendations.append("Continue preserving source traceability for future verification updates.")

    limitations = []
    for result in results:
        for limitation in result.limitations:
            if limitation not in limitations:
                limitations.append(limitation)

    return {
        "document_id": document.id,
        "document_title": document.title,
        "filename": document.filename,
        "processing_status": document.processing_status.value,
        "document_version_id": version.id if version else None,
        "document_version_number": version.version_number if version else None,
        "uploaded_at": document.uploaded_at,
        "generated_at": datetime.now(timezone.utc),
        "total_claims": len(claims),
        "total_citations": len(citations),
        "total_sources": len(sources),
        "total_evidence_passages": evidence_count,
        "verified_claims": len(results),
        "claims_awaiting_review": awaiting,
        "unresolved_claims": unresolved,
        "human_reviewed_claims": human_reviewed,
        "verdict_distribution": distribution,
        "claim_reports": [_claim_report(claim, db) for claim in claims],
        "limitations": limitations,
        "recommendations": recommendations,
        "disclaimer": (
            "This report summarizes evidence and verification metadata. "
            "It is not independently peer-reviewed or scientifically certified."
        ),
    }


def build_claim_report(
    claim_id: UUID,
    current_user: User,
    db: Session,
) -> dict:
    claim = db.get(Claim, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    document = db.get(Document, claim.document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    verify_resource_ownership(document.user_id, current_user)
    return _claim_report(claim, db)


def build_overview_analytics(user: User, db: Session) -> dict:
    documents = list(db.execute(
        select(Document).where(Document.user_id == user.id)
    ).scalars().all())
    document_ids = [document.id for document in documents]
    processed = sum(
        1 for document in documents
        if document.processing_status == DocumentStatus.COMPLETED
    )
    claim_count = len(list(db.execute(
        select(Claim).where(Claim.document_id.in_(document_ids))
    ).scalars().all())) if document_ids else 0
    citation_count = len(list(db.execute(
        select(Citation).where(Citation.document_id.in_(document_ids))
    ).scalars().all())) if document_ids else 0
    source_ids = list(db.execute(
        select(Citation.research_source_id)
        .where(
            Citation.document_id.in_(document_ids),
            Citation.research_source_id.is_not(None),
        )
        .distinct()
    ).scalars().all()) if document_ids else []
    evidence_count = len(list(db.execute(
        select(EvidencePassage)
        .where(EvidencePassage.source_id.in_(source_ids))
    ).scalars().all())) if source_ids else 0
    claim_ids = list(db.execute(
        select(Claim.id).where(Claim.document_id.in_(document_ids))
    ).scalars().all()) if document_ids else []
    results = list(db.execute(
        select(VerificationResult)
        .where(VerificationResult.claim_id.in_(claim_ids))
    ).scalars().all()) if claim_ids else []
    distribution = _distribution(results)
    awaiting = sum(
        1 for result in results
        if result.requires_human_review
        or result.review_status in (
            ReviewStatus.PENDING,
            ReviewStatus.IN_REVIEW,
            ReviewStatus.INVESTIGATION_REQUESTED,
        )
    )
    investigation = sum(
        1 for result in results
        if result.review_status == ReviewStatus.INVESTIGATION_REQUESTED
    )
    human_resolved = sum(
        1 for result in results
        if result.review_status == ReviewStatus.RESOLVED
    )
    completion_rate = (
        human_resolved / len(results)
        if results
        else 0.0
    )
    verified_count = sum(
        1 for result in results
        if result.verification_status == VerificationStatus.COMPLETED
    )
    return {
        "documents_uploaded": len(documents),
        "documents_processed": processed,
        "claims_extracted": claim_count,
        "citations_detected": citation_count,
        "sources_retrieved": len(source_ids),
        "evidence_passages_extracted": evidence_count,
        "claims_verified": verified_count,
        "verdict_distribution": distribution,
        "human_review_completion_rate": round(completion_rate, 4),
        "claims_awaiting_review": awaiting,
        "claims_requiring_investigation": investigation,
    }


def build_document_analytics(
    document_id: UUID,
    current_user: User,
    db: Session,
) -> dict:
    document = _owned_document(document_id, current_user, db)
    report = build_document_report(document_id, current_user, db)
    return {
        "document_id": document.id,
        "documents_uploaded": 1,
        "documents_processed": (
            1 if document.processing_status == DocumentStatus.COMPLETED else 0
        ),
        "claims_extracted": report["total_claims"],
        "citations_detected": report["total_citations"],
        "sources_retrieved": report["total_sources"],
        "evidence_passages_extracted": report["total_evidence_passages"],
        "claims_verified": report["verified_claims"],
        "verdict_distribution": report["verdict_distribution"],
        "human_review_completion_rate": (
            report["human_reviewed_claims"] / report["total_claims"]
            if report["total_claims"]
            else 0.0
        ),
        "claims_awaiting_review": report["claims_awaiting_review"],
        "claims_requiring_investigation": report["unresolved_claims"],
    }


def generate_pdf_report(report: dict) -> bytes:
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    except Exception as exc:
        raise RuntimeError("PDF report dependency is unavailable") from exc

    buffer = BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = [
        Paragraph("ANVEXA AI - Verification Report", styles["Title"]),
        Spacer(1, 12),
        Paragraph(f"Document: {report['document_title']}", styles["Heading1"]),
        Paragraph(f"Filename: {report['filename']}", styles["Normal"]),
        Paragraph(f"Processing status: {report['processing_status']}", styles["Normal"]),
        Paragraph(
            "Executive summary",
            styles["Heading2"],
        ),
        Paragraph(
            f"Claims: {report['total_claims']}; Citations: {report['total_citations']}; "
            f"Sources: {report['total_sources']}; Evidence passages: "
            f"{report['total_evidence_passages']}",
            styles["Normal"],
        ),
    ]
    distribution = report["verdict_distribution"]
    story.append(Paragraph("Verdict statistics", styles["Heading2"]))
    story.append(Paragraph(
        ", ".join(
            f"{name}: {distribution[name]}"
            for name in SIX_VERDICTS
        ),
        styles["Normal"],
    ))
    story.append(Paragraph("Claim-by-claim results", styles["Heading2"]))
    for claim in report["claim_reports"]:
        story.append(Paragraph(
            f"{claim['claim_text']}",
            styles["Heading3"],
        ))
        story.append(Paragraph(
            f"AI verdict: {claim['ai_verdict'] or 'pending'}; "
            f"Human verdict: {claim['human_verdict'] or 'pending'}; "
            f"Result: {claim['result_label']}",
            styles["Normal"],
        ))
        if claim["explanation"]:
            story.append(Paragraph(
                f"Explanation: {claim['explanation']}",
                styles["Normal"],
            ))
        for evidence in claim["supporting_evidence"] + claim["contradicting_evidence"]:
            story.append(Paragraph(
                f"{evidence['relation'].title()} evidence: "
                f"{evidence['evidence_text']} "
                f"[{evidence['publication_title']}"
                f"{'; DOI: ' + evidence['doi'] if evidence['doi'] else ''}]",
                styles["Normal"],
            ))
    story.append(Paragraph("Limitations and disclaimer", styles["Heading2"]))
    for limitation in report["limitations"]:
        story.append(Paragraph(limitation, styles["Normal"]))
    story.append(Paragraph(report["disclaimer"], styles["Normal"]))
    document.build(story)
    return buffer.getvalue()
