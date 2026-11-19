"""Focused tests for Phase 13 reports and analytics."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.database.base import Base
from app.models.document import Claim, Document, DocumentPage, DocumentVersion
from app.models.enums import DocumentStatus, ReviewStatus, Verdict, VerificationStatus
from app.models.research import EvidencePassage, ResearchSource, SourceVersion
from app.models.user import User
from app.models.verification import VerificationResult
from app.services.report_generator.report_service import (
    build_claim_report,
    build_document_report,
    build_overview_analytics,
    generate_pdf_report,
)


@pytest.fixture
def report_db() -> Iterator[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record) -> None:
        connection.cursor().execute("PRAGMA foreign_keys=ON")

    tables = [table for table in Base.metadata.sorted_tables if table.name != "embeddings"]
    Base.metadata.create_all(engine, tables=tables)
    with Session(engine) as session:
        yield session
    engine.dispose()


def make_report_fixture(session: Session) -> tuple[User, Document, Claim, VerificationResult]:
    owner = User(
        email="report-owner@example.test",
        full_name="Report Owner",
        hashed_password="test",
        is_active=True,
    )
    session.add(owner)
    session.flush()
    document = Document(
        user_id=owner.id,
        title="Traceable Report",
        filename="traceable.pdf",
        storage_path="documents/traceable.pdf",
        file_hash="a" * 64,
        file_type="application/pdf",
        file_size=8192,
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
        page_number=4,
        extracted_text="The sample improved by 25 percent.",
        metadata_json={},
    )
    session.add(page)
    session.flush()
    claim = Claim(
        document_id=document.id,
        document_version_id=version.id,
        page_id=page.id,
        page_number=4,
        paragraph_number=1,
        section_heading="Results",
        original_text="The sample improved by 25 percent.",
        normalized_text="The sample improved by 25 percent.",
        claim_type="statistical",
        citation_markers=["[1]"],
    )
    session.add(claim)
    source = ResearchSource(
        title="Supporting Trial",
        doi="10.1234/report",
        authors=["A. Researcher"],
        publication_year=2024,
        source_url="https://doi.org/10.1234/report",
        abstract="The trial reported a 25 percent improvement.",
    )
    session.add(source)
    session.flush()
    source_version = SourceVersion(
        source_id=source.id,
        content_sha256="b" * 64,
        full_text_available=False,
    )
    session.add(source_version)
    session.flush()
    evidence = EvidencePassage(
        source_id=source.id,
        claim_id=claim.id,
        source_version_id=source_version.id,
        passage_index=1,
        passage_text="The trial reported a 25 percent improvement.",
        section_name="Results",
        page_number=5,
        paragraph_number=2,
        content_type="abstract",
        extraction_method="source_metadata_abstract",
        source_url=source.source_url,
        doi=source.doi,
        passage_hash="c" * 64,
    )
    session.add(evidence)
    session.flush()
    result = VerificationResult(
        claim_id=claim.id,
        document_version_id=version.id,
        verdict=Verdict.PARTLY_SUPPORTED,
        final_verdict=Verdict.PARTLY_SUPPORTED,
        explanation="The result is partially consistent with the source.",
        confidence="medium",
        confidence_score=0.62,
        verification_status=VerificationStatus.COMPLETED,
        structured_analysis={"scope_assessment": "Limited population"},
        supporting_evidence_ids=[str(evidence.id)],
        contradicting_evidence_ids=[],
        limitations=["Full text was unavailable."],
        unresolved_questions=["Confirm the complete population."],
        model_provider="gemini",
        model_name="gemini-test",
        prompt_version="phase10-v1",
        requires_human_review=True,
        review_status=ReviewStatus.PENDING,
        verified_at=datetime.now(timezone.utc),
    )
    session.add(result)
    session.commit()
    return owner, document, claim, result


def test_document_report_traceability(report_db: Session) -> None:
    owner, document, claim, result = make_report_fixture(report_db)
    report = build_document_report(document.id, owner, report_db)
    assert report["document_title"] == "Traceable Report"
    assert report["total_claims"] == 1
    assert report["total_evidence_passages"] == 1
    assert report["claim_reports"][0]["claim_text"] == claim.original_text
    assert report["claim_reports"][0]["page_number"] == 4
    assert report["claim_reports"][0]["supporting_evidence"][0]["doi"] == "10.1234/report"
    assert report["claim_reports"][0]["limitations"] == ["Full text was unavailable."]


def test_claim_report_preserves_ai_human_separation(report_db: Session) -> None:
    owner, document, claim, result = make_report_fixture(report_db)
    result.final_verdict = Verdict.SUPPORTED
    report_db.commit()
    report = build_claim_report(claim.id, owner, report_db)
    assert report["ai_verdict"] == Verdict.PARTLY_SUPPORTED
    assert report["human_verdict"] is None
    assert report["final_verdict"] == Verdict.SUPPORTED
    assert report["result_label"] == "ai_generated"


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
def test_all_verdict_categories(report_db: Session, verdict: Verdict) -> None:
    owner, document, claim, result = make_report_fixture(report_db)
    result.final_verdict = verdict
    report_db.commit()
    report = build_document_report(document.id, owner, report_db)
    assert report["verdict_distribution"][verdict.value] == 1


def test_empty_document_report(report_db: Session) -> None:
    owner = User(
        email="empty-report@example.test",
        full_name="Empty Report",
        hashed_password="test",
        is_active=True,
    )
    report_db.add(owner)
    report_db.flush()
    document = Document(
        user_id=owner.id,
        title="Empty",
        filename="empty.pdf",
        storage_path="documents/empty.pdf",
        file_hash="d" * 64,
        file_type="application/pdf",
        file_size=1,
        processing_status=DocumentStatus.UPLOADED,
    )
    report_db.add(document)
    report_db.commit()
    report = build_document_report(document.id, owner, report_db)
    assert report["total_claims"] == 0
    assert report["total_citations"] == 0
    assert report["claim_reports"] == []


def test_analytics_use_database_records(report_db: Session) -> None:
    owner, document, claim, result = make_report_fixture(report_db)
    analytics = build_overview_analytics(owner, report_db)
    assert analytics["documents_uploaded"] == 1
    assert analytics["documents_processed"] == 1
    assert analytics["claims_extracted"] == 1
    assert analytics["evidence_passages_extracted"] == 1
    assert analytics["claims_verified"] == 1


def test_pdf_export(report_db: Session) -> None:
    owner, document, claim, result = make_report_fixture(report_db)
    report = build_document_report(document.id, owner, report_db)
    try:
        pdf = generate_pdf_report(report)
    except RuntimeError:
        pytest.skip("ReportLab is not installed")
    assert pdf.startswith(b"%PDF")


def test_cross_user_report_denied(report_db: Session) -> None:
    owner, document, claim, result = make_report_fixture(report_db)
    other = User(
        email="other-report@example.test",
        full_name="Other",
        hashed_password="test",
        is_active=True,
    )
    report_db.add(other)
    report_db.commit()
    with pytest.raises(HTTPException) as exc:
        build_document_report(document.id, other, report_db)
    assert exc.value.status_code == 403
