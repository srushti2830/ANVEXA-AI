"""Tests for Phase 7 citation detection and mapping."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.database.base import Base
from app.models.document import (
    Citation,
    Claim,
    ClaimCitation,
    Document,
    DocumentPage,
    DocumentVersion,
)
from app.models.enums import (
    CitationMappingStatus,
    CitationStyle,
    DocumentStatus,
)
from app.models.user import User
from app.services.citation_detector.citation_detector import (
    detect_citations,
    detect_markers,
    extract_reference_entry,
    normalize_marker,
)


@pytest.fixture
def citation_db() -> Iterator[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record) -> None:
        connection.cursor().execute("PRAGMA foreign_keys=ON")

    tables = [table for table in Base.metadata.sorted_tables if table.name != "embeddings"]
    Base.metadata.create_all(engine, tables=tables)
    with Session(engine) as session:
        yield session
    engine.dispose()


def make_parsed_document(session: Session, text: str) -> tuple[User, Document, DocumentVersion]:
    user = User(
        email="citation-owner@example.test",
        full_name="Citation Owner",
        hashed_password="test",
        is_active=True,
    )
    session.add(user)
    session.flush()
    document = Document(
        user_id=user.id,
        title="Cited report",
        filename="report.pdf",
        storage_path="documents/report.pdf",
        file_hash="c" * 64,
        file_type="application/pdf",
        file_size=2048,
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
    session.add(DocumentPage(
        document_id=document.id,
        document_version_id=version.id,
        page_number=2,
        extracted_text=text,
        metadata_json={},
    ))
    session.commit()
    return user, document, version


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Results were reported (Smith et al., 2023).", "(Smith et al., 2023)"),
        ("Smith and Jones (2022) found an effect.", "Smith and Jones (2022)"),
        ("The value was reported [2, 4, 6].", "[2, 4, 6]"),
        ("This follows WHO guidance (WHO, 2024).", "(WHO, 2024)"),
    ],
)
def test_marker_preservation(text: str, expected: str) -> None:
    markers = detect_markers(text, 2, 0)
    assert any(marker.original == expected for marker in markers)


def test_numeric_normalization_and_duplicates() -> None:
    normalized = normalize_marker("[2, 4, 6]")
    assert normalized == "numeric:2,4,6"
    assert normalize_marker("[02]") == "numeric:2"


def test_author_year_suffix_normalization() -> None:
    assert normalize_marker("(Smith, 2022b)") == "author_year:smith, 2022b"


def test_reference_entry_preserves_available_fields() -> None:
    entry = (
        "Jones, A. 2021. A study. Journal of Testing, 12(3), "
        "10-20. https://example.test/paper doi:10.1234/EXAMPLE"
    )
    fields = extract_reference_entry(entry)
    assert fields["publication_year"] == 2021
    assert fields["volume"] == "12"
    assert fields["issue"] == "3"
    assert fields["page_range"] == "10-20"
    assert fields["doi"] == "10.1234/EXAMPLE"
    assert fields["url"] == "https://example.test/paper"


def test_missing_bibliographic_fields_are_not_invented() -> None:
    fields = extract_reference_entry("[7] Smith. 2020.")
    assert fields["reference_number"] == "7"
    assert fields["publication_year"] == 2020
    assert fields["publication_title"] is None


def test_database_mapping_persistence_and_duplicate_guard(citation_db: Session) -> None:
    user, document, version = make_parsed_document(
        citation_db,
        "References\n[1] Smith, A. 2023. Testing methods.",
    )
    claim = Claim(
        document_id=document.id,
        document_version_id=version.id,
        page_number=2,
        paragraph_number=0,
        original_text="The study reported [1].",
        normalized_text="The study reported [1].",
        claim_type="scientific",
        extraction_status="completed",
    )
    citation_db.add(claim)
    citation_db.flush()
    citation = Citation(
        document_id=document.id,
        document_version_id=version.id,
        citation_text="[1]",
        original_marker="[1]",
        normalized_marker="numeric:1",
        citation_type=CitationStyle.NUMERIC,
        reference_number="1",
        page_number=2,
        paragraph_number=0,
        is_bibliography_entry=False,
        extraction_method="rule_based",
    )
    citation_db.add(citation)
    citation_db.flush()
    link = ClaimCitation(
        claim_id=claim.id,
        citation_id=citation.id,
        citation_text="[1]",
        normalized_marker="numeric:1",
        page_number=2,
        paragraph_number=0,
        mapping_status=CitationMappingStatus.MATCHED,
        mapping_method="exact_normalized_marker",
    )
    citation_db.add(link)
    citation_db.commit()
    assert citation_db.query(ClaimCitation).count() == 1
    assert citation_db.query(Citation).one().normalized_marker == "numeric:1"


def test_repeated_doi_markers_are_deduplicated(citation_db: Session) -> None:
    user, document, version = make_parsed_document(
        citation_db,
        "The DOI is 10.1038/sdata.2016.18.\n\n"
        "This later passage repeats DOI 10.1038/sdata.2016.18.",
    )
    result = detect_citations(document.id, user, citation_db)

    assert result["detected_count"] == 1
    assert citation_db.query(Citation).count() == 1
