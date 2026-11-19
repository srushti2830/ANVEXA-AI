"""Targeted tests for deterministic Phase 11 verdict classification."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.database.base import Base
from app.models.document import Claim, Document, DocumentPage, DocumentVersion
from app.models.enums import (
    DocumentStatus,
    Verdict,
    VerificationStatus,
)
from app.models.user import User
from app.models.verification import VerificationEvidence, VerificationResult
from app.services.verdict_classifier.verdict_classifier import (
    classify_claim,
    classify_verification_result,
)


@pytest.fixture
def verdict_db() -> Iterator[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record) -> None:
        connection.cursor().execute("PRAGMA foreign_keys=ON")

    tables = [table for table in Base.metadata.sorted_tables if table.name != "embeddings"]
    Base.metadata.create_all(engine, tables=tables)
    with Session(engine) as session:
        yield session
    engine.dispose()


def make_result(
    verdict: Verdict,
    *,
    supporting: list[str] | None = None,
    contradicting: list[str] | None = None,
    status: VerificationStatus = VerificationStatus.COMPLETED,
    review: bool = False,
    structured: dict | None = None,
) -> VerificationResult:
    return VerificationResult(
        claim_id="00000000-0000-0000-0000-000000000001",
        document_version_id="00000000-0000-0000-0000-000000000002",
        verdict=verdict,
        explanation="Deterministic test analysis.",
        confidence_score=0.8,
        verification_status=status,
        structured_analysis=structured or {},
        supporting_evidence_ids=supporting or [],
        contradicting_evidence_ids=contradicting or [],
        limitations=[],
        unresolved_questions=[],
        model_provider="gemini",
        model_name="gemini-test",
        prompt_version="phase10-v1",
        requires_human_review=review,
        verified_at=datetime.now(timezone.utc),
    )


@pytest.mark.parametrize(
    ("verdict", "supporting", "contradicting", "structured", "expected"),
    [
        (Verdict.SUPPORTED, ["e-1"], [], {}, Verdict.SUPPORTED),
        (Verdict.PARTLY_SUPPORTED, ["e-1"], [], {"scope_assessment": "partial"}, Verdict.PARTLY_SUPPORTED),
        (Verdict.UNSUPPORTED, [], [], {}, Verdict.UNSUPPORTED),
        (Verdict.CONTRADICTORY, ["e-1"], ["e-2"], {}, Verdict.CONTRADICTORY),
        (
            Verdict.POSSIBLY_OUTDATED,
            ["e-1"],
            [],
            {"temporal_assessment": "potentially outdated"},
            Verdict.POSSIBLY_OUTDATED,
        ),
    ],
)
def test_all_non_review_categories(
    verdict: Verdict,
    supporting: list[str],
    contradicting: list[str],
    structured: dict,
    expected: Verdict,
) -> None:
    result = make_result(
        verdict,
        supporting=supporting,
        contradicting=contradicting,
        structured=structured,
    )
    final, reason, confidence = classify_verification_result(result)
    assert final == expected
    assert reason
    assert 0.0 <= confidence <= 1.0


def test_needs_review_without_evidence() -> None:
    result = make_result(Verdict.NEEDS_REVIEW)
    final, reason, confidence = classify_verification_result(result)
    assert final == Verdict.NEEDS_REVIEW
    assert "supporting" in reason.lower() or "review" in reason.lower()
    assert confidence <= 0.25


def test_failed_verification_requires_review() -> None:
    result = make_result(
        Verdict.NEEDS_REVIEW,
        status=VerificationStatus.FAILED,
    )
    final, reason, confidence = classify_verification_result(result)
    assert final == Verdict.NEEDS_REVIEW
    assert confidence == 0.0


def make_persisted_claim(session: Session) -> tuple[User, Document, Claim, VerificationResult]:
    user = User(
        email="verdict-owner@example.test",
        full_name="Verdict Owner",
        hashed_password="test",
        is_active=True,
    )
    session.add(user)
    session.flush()
    document = Document(
        user_id=user.id,
        title="Verdict report",
        filename="report.pdf",
        storage_path="documents/report.pdf",
        file_hash="8" * 64,
        file_type="application/pdf",
        file_size=4096,
        processing_status=DocumentStatus.COMPLETED,
    )
    session.add(document)
    session.flush()
    version = DocumentVersion(
        document_id=document.id,
        version_number=1,
        storage_key=document.storage_path,
        content_sha256=document.file_hash,
    )
    session.add(version)
    session.flush()
    page = DocumentPage(
        document_id=document.id,
        document_version_id=version.id,
        page_number=1,
        extracted_text="The study found an improvement.",
        metadata_json={},
    )
    session.add(page)
    session.flush()
    claim = Claim(
        document_id=document.id,
        document_version_id=version.id,
        page_id=page.id,
        page_number=1,
        paragraph_number=0,
        original_text="The study found an improvement.",
        normalized_text="The study found an improvement.",
        claim_type="scientific",
    )
    session.add(claim)
    session.flush()
    result = VerificationResult(
        claim_id=claim.id,
        document_version_id=version.id,
        verdict=Verdict.SUPPORTED,
        explanation="Direct supporting evidence was supplied.",
        confidence_score=0.85,
        verification_status=VerificationStatus.COMPLETED,
        structured_analysis={"semantic_alignment": "direct"},
        supporting_evidence_ids=["e-1"],
        contradicting_evidence_ids=[],
        limitations=[],
        unresolved_questions=[],
        model_provider="gemini",
        model_name="gemini-test",
        prompt_version="phase10-v1",
        verified_at=datetime.now(timezone.utc),
    )
    session.add(result)
    session.commit()
    return user, document, claim, result


def test_persisted_classification_is_idempotent(verdict_db: Session) -> None:
    user, document, claim, result = make_persisted_claim(verdict_db)
    first = classify_claim(claim.id, user, verdict_db)
    classified_at = first["classified_at"]
    second = classify_claim(claim.id, user, verdict_db)
    assert first["final_verdict"] == Verdict.SUPPORTED
    assert second["final_verdict"] == Verdict.SUPPORTED
    assert second["classified_at"] == classified_at
    assert verdict_db.query(VerificationResult).filter_by(claim_id=claim.id).count() == 1


def test_cross_user_classification_denied(verdict_db: Session) -> None:
    owner, document, claim, result = make_persisted_claim(verdict_db)
    other = User(
        email="other-verdict@example.test",
        full_name="Other User",
        hashed_password="test",
        is_active=True,
    )
    verdict_db.add(other)
    verdict_db.commit()
    with pytest.raises(HTTPException) as exc:
        classify_claim(claim.id, other, verdict_db)
    assert exc.value.status_code == 403
