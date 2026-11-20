"""Tests for Phase 8 research source metadata retrieval."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.database.base import Base
from app.models.document import Citation, Document, DocumentVersion
from app.models.enums import DocumentStatus, RetrievalStatus
from app.models.research import ResearchSource, SourceVersion
from app.models.user import User
from app.services.source_retriever.source_retriever import (
    lookup_crossref_by_doi,
    lookup_openalex_by_doi,
    lookup_semantic_scholar_by_doi,
    lookup_europe_pmc_by_doi,
    normalize_doi,
)


@pytest.fixture
def source_db() -> Iterator[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record) -> None:
        connection.cursor().execute("PRAGMA foreign_keys=ON")

    tables = [table for table in Base.metadata.sorted_tables if table.name != "embeddings"]
    Base.metadata.create_all(engine, tables=tables)
    with Session(engine) as session:
        yield session
    engine.dispose()


def make_document(session: Session) -> tuple[User, Document, DocumentVersion]:
    user = User(
        email="source-owner@example.test",
        full_name="Source Owner",
        hashed_password="test",
        is_active=True,
    )
    session.add(user)
    session.flush()
    document = Document(
        user_id=user.id,
        title="Source report",
        filename="report.pdf",
        storage_path="documents/report.pdf",
        file_hash="d" * 64,
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
    session.commit()
    return user, document, version


def test_doi_normalization() -> None:
    assert normalize_doi("https://doi.org/10.1234/ABC.DEF") == "10.1234/abc.def"
    assert normalize_doi("not a doi") is None


def test_database_source_persistence_and_doi_deduplication(source_db: Session) -> None:
    user, document, version = make_document(source_db)
    citation = Citation(
        document_id=document.id,
        document_version_id=version.id,
        citation_text="[1]",
        original_marker="[1]",
        normalized_marker="numeric:1",
        citation_type="numeric",
        doi="10.1234/test",
        is_bibliography_entry=True,
        extraction_method="rule_based",
    )
    source_db.add(citation)
    source_db.flush()
    source = ResearchSource(
        doi="10.1234/test",
        title="Testing DOI Metadata",
        authors=["A. Smith"],
        publication_year=2023,
        journal="Testing Journal",
        source_url="https://doi.org/10.1234/test",
        retrieval_status=RetrievalStatus.METADATA_ONLY,
    )
    source_db.add(source)
    source_db.flush()
    snapshot = SourceVersion(
        source_id=source.id,
        version_url=source.source_url,
        content_sha256="e" * 64,
        full_text_available=False,
    )
    source_db.add(snapshot)
    citation.research_source_id = source.id
    source_db.commit()

    assert source_db.query(ResearchSource).count() == 1
    assert source_db.query(SourceVersion).count() == 1
    assert source_db.query(Citation).one().research_source_id == source.id


def test_crossref_doi_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    response = {
        "message": {
            "DOI": "10.1234/test",
            "title": ["Test Article"],
            "author": [{"given": "Ada", "family": "Lovelace"}],
            "published-print": {"date-parts": [[2024]]},
            "container-title": ["Test Journal"],
            "URL": "https://doi.org/10.1234/test",
        }
    }
    monkeypatch.setattr(
        "app.services.source_retriever.source_retriever._request_json",
        lambda *args, **kwargs: response,
    )
    metadata = lookup_crossref_by_doi("10.1234/test")
    assert metadata is not None
    assert metadata["title"] == "Test Article"
    assert metadata["authors"] == ["Ada Lovelace"]
    assert metadata["publication_year"] == 2024
    assert metadata["journal"] == "Test Journal"


def test_semantic_scholar_doi_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    response = {
        "paperId": "abc123",
        "title": "Semantic Scholar Test Article",
        "authors": [{"name": "Ada Lovelace"}],
        "year": 2024,
        "venue": "Test Journal",
        "doi": "10.1234/test",
        "abstract": "A real provider abstract.",
    }
    monkeypatch.setattr(
        "app.services.source_retriever.source_retriever._request_json",
        lambda *args, **kwargs: response,
    )
    metadata = lookup_semantic_scholar_by_doi("10.1234/test")
    assert metadata is not None
    assert metadata["provider"] == "semantic_scholar"
    assert metadata["title"] == "Semantic Scholar Test Article"
    assert metadata["authors"] == ["Ada Lovelace"]


def test_europe_pmc_doi_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    response = {
        "resultList": {
            "result": [{
                "id": "PMC123",
                "pmcid": "PMC123",
                "doi": "10.1234/test",
                "title": "Europe PMC Test Article",
                "authorString": "Smith A, Jones B",
                "pubYear": "2024",
                "journalTitle": "Test Journal",
            }]
        }
    }
    monkeypatch.setattr(
        "app.services.source_retriever.source_retriever._request_json",
        lambda *args, **kwargs: response,
    )
    metadata = lookup_europe_pmc_by_doi("10.1234/test")
    assert metadata is not None
    assert metadata["provider"] == "europe_pmc"
    assert metadata["title"] == "Europe PMC Test Article"
    assert metadata["publication_year"] == 2024


@pytest.mark.skipif(
    os.getenv("ANVEXA_LIVE_PROVIDER_TESTS") != "true",
    reason="Live provider test mode is not enabled",
)
@pytest.mark.parametrize(
    "lookup",
    [
        lookup_crossref_by_doi,
        lookup_openalex_by_doi,
        lookup_europe_pmc_by_doi,
    ],
)
def test_live_provider_doi_lookup(lookup) -> None:
    metadata = lookup("10.1038/sdata.2016.18")
    assert metadata is not None
    assert "FAIR" in metadata["title"]


def test_missing_metadata_does_not_create_fabricated_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.source_retriever.source_retriever.lookup_crossref_by_doi",
        lambda doi: None,
    )
    monkeypatch.setattr(
        "app.services.source_retriever.source_retriever.lookup_openalex_by_doi",
        lambda doi: None,
    )
    monkeypatch.setattr(
        "app.services.source_retriever.source_retriever.lookup_crossref_by_query",
        lambda citation: None,
    )
    citation = Citation(
        document_id="00000000-0000-0000-0000-000000000001",
        document_version_id="00000000-0000-0000-0000-000000000002",
        citation_text="Smith, 2024.",
        citation_type="author_year",
        is_bibliography_entry=True,
    )
    from app.services.source_retriever.source_retriever import retrieve_metadata

    assert retrieve_metadata(citation) is None
