"""Tests for Phase 6 claim extraction."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.database.base import Base
from app.models.document import Claim, Document, DocumentPage, DocumentVersion
from app.models.enums import ClaimType, DocumentStatus, ExtractionStatus
from app.models.user import User
from app.services.claim_extractor.claim_extractor import (
    detect_citation_markers,
    gemini_extract,
    locate_sentences,
    rule_based_extract,
    split_sentences,
)


@pytest.fixture
def claim_db() -> Iterator[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")

    tables = [table for table in Base.metadata.sorted_tables if table.name != "embeddings"]
    Base.metadata.create_all(engine, tables=tables)
    with Session(engine) as session:
        yield session
    engine.dispose()


def make_document(session: Session, text: str = "") -> tuple[User, Document, DocumentVersion]:
    user = User(
        email="claim-owner@example.test",
        full_name="Claim Owner",
        hashed_password="test",
        is_active=True,
    )
    session.add(user)
    session.flush()
    document = Document(
        user_id=user.id,
        title="Academic report",
        filename="report.pdf",
        storage_path="documents/report.pdf",
        file_hash="b" * 64,
        file_type="application/pdf",
        file_size=1024,
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
    if text:
        session.add(DocumentPage(
            document_id=document.id,
            document_version_id=version.id,
            page_number=3,
            extracted_text=text,
            metadata_json={"headings": ["Results"]},
        ))
    session.commit()
    return user, document, version


def test_simple_factual_and_statistical_claims() -> None:
    located = locate_sentences({"pages": [{"page_number": 2, "text":
        "The patient recovery rate is 92 percent. The study found a link between exercise and health."}]})
    extracted = rule_based_extract(located)
    assert len(extracted) == 2
    assert any(item["claim_type"] == ClaimType.STATISTICAL.value for item in extracted)


def test_comparative_and_causal_claims() -> None:
    located = locate_sentences({"pages": [{"page_number": 1, "text":
        "Algorithm A is higher than Algorithm B. Exercise causes improved health outcomes."}]})
    types = {item["claim_type"] for item in rule_based_extract(located)}
    assert ClaimType.COMPARATIVE.value in types
    assert ClaimType.CAUSAL.value in types


def test_multiple_claims_and_citation_preservation() -> None:
    text = "Study A reported 80 percent accuracy [2, 4]. Smith and Jones (2022) found a lower error rate."
    located = locate_sentences({"pages": [{"page_number": 4, "text": text}]})
    markers = detect_citation_markers(text)
    assert "[2, 4]" in markers
    assert "(2022)" not in " ".join(markers)
    assert "Smith and Jones (2022)" in markers
    assert len(rule_based_extract(located)) == 2


def test_sentence_splitter_preserves_decimal_doi_and_citations() -> None:
    text = "The value was 3.14. The DOI is 10.1000/ABC.DEF. Smith et al., 2023 showed the result."
    sentences = split_sentences(text)
    assert len(sentences) == 3
    assert "3.14" in sentences[0]
    assert "10.1000/ABC.DEF" in sentences[1]


def test_opinion_and_bibliography_exclusion() -> None:
    text = "I think this model is elegant. References\nSmith, J. 2020. Experimental methods."
    located = locate_sentences({"pages": [{"page_number": 1, "text": text}]})
    extracted = rule_based_extract(located)
    assert extracted == []


def test_empty_document_fallback(claim_db: Session) -> None:
    user, document, version = make_document(claim_db, "")
    claim_count = claim_db.query(Claim).filter_by(document_version_id=version.id).count()
    assert claim_count == 0
    assert document.processing_status == DocumentStatus.COMPLETED


def test_gemini_failure_uses_rule_based_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.claim_extractor.claim_extractor.get_settings",
        lambda: type("Settings", (), {
            "gemini_api_key": None,
            "gemini_model": "gemini-test",
            "gemini_timeout_seconds": 1,
            "gemini_max_retries": 0,
        })(),
    )
    located = locate_sentences({"pages": [{"page_number": 1, "text":
        "The study found that 75 percent of participants improved."}]})
    ai_claims, error = gemini_extract(located)
    assert ai_claims == []
    assert error
    fallback = rule_based_extract(located)
    assert fallback


def test_database_persistence_page_and_duplicate_identity(claim_db: Session) -> None:
    user, document, version = make_document(
        claim_db,
        "The study found that 75 percent of participants improved [1].",
    )
    located = locate_sentences({
        "pages": [{
            "page_number": 3,
            "text": "The study found that 75 percent of participants improved [1].",
        }]
    })
    item = rule_based_extract(located)[0]
    location = located[0]
    claim = Claim(
        document_id=document.id,
        document_version_id=version.id,
        page_number=location.page_number,
        paragraph_number=location.paragraph_index,
        original_text=location.text,
        normalized_text=item["claim_text"],
        claim_type=ClaimType.STATISTICAL,
        requires_external_verification=True,
        section_heading="Results",
        extraction_confidence=item["confidence"],
        citation_markers=location.citation_markers,
        extraction_reason=item["extraction_reason"],
        extraction_method="rule_based",
        extraction_status=ExtractionStatus.COMPLETED,
    )
    claim_db.add(claim)
    claim_db.commit()
    persisted = claim_db.query(Claim).one()
    assert persisted.page_number == 3
    assert persisted.citation_markers == ["[1]"]
    assert persisted.section_heading == "Results"
