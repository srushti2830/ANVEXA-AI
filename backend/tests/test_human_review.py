"""Focused tests for the Phase 12 human-review workflow."""

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
    ReviewAction,
    ReviewStatus,
    UserRole,
    Verdict,
    VerificationStatus,
)
from app.models.research import EvidencePassage, ResearchSource, SourceVersion
from app.models.user import User
from app.models.verification import ReviewHistory, VerificationResult
from app.services.human_review.human_review_service import (
    get_review_detail,
    get_review_history,
    get_review_queue,
    request_investigation,
    submit_human_review,
)


@pytest.fixture
def review_db() -> Iterator[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record) -> None:
        connection.cursor().execute("PRAGMA foreign_keys=ON")

    tables = [table for table in Base.metadata.sorted_tables if table.name != "embeddings"]
    Base.metadata.create_all(engine, tables=tables)
    with Session(engine) as session:
        yield session
    engine.dispose()


def make_review_fixture(
    session: Session,
    *,
    reviewer_role: UserRole = UserRole.REVIEWER,
) -> tuple[User, User, Document, Claim, VerificationResult, EvidencePassage]:
    owner = User(
        email="review-owner@example.test",
        full_name="Review Owner",
        hashed_password="test",
        role=UserRole.USER,
        is_active=True,
    )
    reviewer = User(
        email="reviewer@example.test",
        full_name="Human Reviewer",
        hashed_password="test",
        role=reviewer_role,
        is_active=True,
    )
    session.add_all([owner, reviewer])
    session.flush()
    document = Document(
        user_id=owner.id,
        title="Reviewable report",
        filename="report.pdf",
        storage_path="documents/report.pdf",
        file_hash="9" * 64,
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
        page_number=3,
        extracted_text="The trial found a 20 percent improvement.",
        metadata_json={},
    )
    session.add(page)
    session.flush()
    claim = Claim(
        document_id=document.id,
        document_version_id=version.id,
        page_id=page.id,
        page_number=3,
        paragraph_number=0,
        original_text="The trial found a 20 percent improvement.",
        normalized_text="The trial found a 20 percent improvement.",
        claim_type="statistical",
        citation_markers=["[1]"],
    )
    session.add(claim)
    session.flush()
    source = ResearchSource(
        title="Clinical Trial",
        doi="10.1234/review",
        authors=["A. Researcher"],
        publication_year=2024,
        source_url="https://doi.org/10.1234/review",
        abstract="The trial reported a 20 percent improvement.",
    )
    session.add(source)
    session.flush()
    source_version = SourceVersion(
        source_id=source.id,
        content_sha256="a" * 64,
        full_text_available=False,
    )
    session.add(source_version)
    session.flush()
    evidence = EvidencePassage(
        source_id=source.id,
        claim_id=claim.id,
        source_version_id=source_version.id,
        passage_index=1,
        passage_text="The trial reported a 20 percent improvement.",
        section_name="Results",
        page_number=3,
        paragraph_number=1,
        content_type="abstract",
        extraction_method="source_metadata_abstract",
        source_url=source.source_url,
        doi=source.doi,
        passage_hash="b" * 64,
    )
    session.add(evidence)
    session.flush()
    result = VerificationResult(
        claim_id=claim.id,
        document_version_id=version.id,
        verdict=Verdict.PARTLY_SUPPORTED,
        final_verdict=Verdict.PARTLY_SUPPORTED,
        explanation="The evidence partially matches the claim.",
        confidence_score=0.55,
        verification_status=VerificationStatus.COMPLETED,
        structured_analysis={"scope_assessment": "Limited population"},
        supporting_evidence_ids=[str(evidence.id)],
        contradicting_evidence_ids=[],
        limitations=["The evidence is an abstract only."],
        unresolved_questions=["Full text is unavailable."],
        model_provider="gemini",
        model_name="gemini-test",
        prompt_version="phase10-v1",
        requires_human_review=True,
        review_status=ReviewStatus.PENDING,
        classified_at=datetime.now(timezone.utc),
        verified_at=datetime.now(timezone.utc),
    )
    session.add(result)
    session.commit()
    return owner, reviewer, document, claim, result, evidence


def test_review_queue_filter_and_detail(review_db: Session) -> None:
    owner, reviewer, document, claim, result, evidence = make_review_fixture(review_db)
    queue = get_review_queue(
        reviewer,
        review_db,
        document_id=document.id,
        verdict=Verdict.PARTLY_SUPPORTED,
        page=1,
        per_page=20,
    )
    assert queue["pagination"]["total"] == 1
    assert queue["reviews"][0]["claim_id"] == claim.id

    detail = get_review_detail(result.id, reviewer, review_db)
    assert detail["claim_text"] == claim.original_text
    assert detail["supporting_evidence"][0]["evidence_text"] == evidence.passage_text
    assert detail["limitations"] == ["The evidence is an abstract only."]
    assert detail["ai_verdict"] == Verdict.PARTLY_SUPPORTED


@pytest.mark.parametrize(
    "verdict",
    [
        Verdict.SUPPORTED,
        Verdict.PARTLY_SUPPORTED,
        Verdict.UNSUPPORTED,
        Verdict.CONTRADICTORY,
        Verdict.POSSIBLY_OUTDATED,
        Verdict.NEEDS_REVIEW,
    ],
)
def test_submit_human_verdict_options(review_db: Session, verdict: Verdict) -> None:
    owner, reviewer, document, claim, result, evidence = make_review_fixture(review_db)
    review = submit_human_review(
        result.id,
        verdict,
        "The reviewer examined the supplied abstract and source limitations.",
        "Additional reviewer notes.",
        [evidence.id],
        reviewer,
        review_db,
    )
    assert review["human_verdict"] == verdict
    assert review["reviewer_id"] == reviewer.id
    assert review_db.query(ReviewHistory).filter_by(
        verification_result_id=result.id
    ).count() == 1
    assert result.review_status == ReviewStatus.RESOLVED


def test_missing_explanation_validation(review_db: Session) -> None:
    owner, reviewer, document, claim, result, evidence = make_review_fixture(review_db)
    with pytest.raises(HTTPException) as exc:
        submit_human_review(
            result.id,
            Verdict.SUPPORTED,
            "Too short",
            None,
            [],
            reviewer,
            review_db,
        )
    assert exc.value.status_code == 422


def test_cross_user_user_cannot_review(review_db: Session) -> None:
    owner, reviewer, document, claim, result, evidence = make_review_fixture(review_db)
    ordinary = User(
        email="ordinary@example.test",
        full_name="Ordinary",
        hashed_password="test",
        role=UserRole.USER,
        is_active=True,
    )
    review_db.add(ordinary)
    review_db.commit()
    with pytest.raises(HTTPException) as exc:
        get_review_detail(result.id, ordinary, review_db)
    assert exc.value.status_code == 403


def test_duplicate_submission_is_idempotent(review_db: Session) -> None:
    owner, reviewer, document, claim, result, evidence = make_review_fixture(review_db)
    first = submit_human_review(
        result.id,
        Verdict.SUPPORTED,
        "The reviewer found direct support in the source abstract.",
        None,
        [evidence.id],
        reviewer,
        review_db,
    )
    second = submit_human_review(
        result.id,
        Verdict.UNSUPPORTED,
        "A different verdict should not create a duplicate submission.",
        None,
        [],
        reviewer,
        review_db,
    )
    assert first["id"] == second["id"]
    assert review_db.query(ReviewHistory).filter_by(
        verification_result_id=result.id
    ).count() == 1


def test_investigation_request_and_history(review_db: Session) -> None:
    owner, reviewer, document, claim, result, evidence = make_review_fixture(review_db)
    action = request_investigation(
        result.id,
        "The full text and source methodology are needed for this decision.",
        "Please investigate publication limitations.",
        [evidence.id],
        reviewer,
        review_db,
    )
    assert action["action"] == ReviewAction.REQUEST_INVESTIGATION
    assert result.review_status == ReviewStatus.INVESTIGATION_REQUESTED
    history = get_review_history(result.id, reviewer, review_db)
    assert history["pagination"]["total"] == 1
    assert history["history"][0]["reviewer_id"] == reviewer.id


def test_ai_verdict_is_preserved(review_db: Session) -> None:
    owner, reviewer, document, claim, result, evidence = make_review_fixture(review_db)
    original = result.verdict
    submit_human_review(
        result.id,
        Verdict.UNSUPPORTED,
        "Human review found that the evidence does not support the claim.",
        None,
        [evidence.id],
        reviewer,
        review_db,
    )
    assert result.final_verdict == Verdict.UNSUPPORTED
    assert result.verdict == original
