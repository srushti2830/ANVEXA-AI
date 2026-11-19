"""Targeted tests for Phase 9 evidence extraction and embeddings."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
import pymupdf
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.database.base import Base
from app.models.document import Document, DocumentVersion
from app.models.enums import DocumentStatus
from app.models.research import Embedding, EvidencePassage, ResearchSource, SourceVersion
from app.models.user import User
from app.services.evidence_engine.evidence_engine import (
    chunk_text,
    cosine_similarity,
    deduplicate_chunks,
    generate_embeddings,
    parse_html,
    parse_xml,
    extract_pdf_text,
)


@pytest.fixture
def evidence_db() -> Iterator[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record) -> None:
        connection.cursor().execute("PRAGMA foreign_keys=ON")

    tables = [table for table in Base.metadata.sorted_tables if table.name != "embeddings"]
    Base.metadata.create_all(engine, tables=tables)
    with Session(engine) as session:
        yield session
    engine.dispose()


def test_chunking_preserves_sentences_numbers_units_and_terminology() -> None:
    text = (
        "The HbA1c concentration decreased by 0.8 mmol/mol in the intervention group. "
        "The 95% confidence interval was preserved for p < 0.001."
    )
    chunks = chunk_text(text, section_name="Results", max_chars=70)
    assert len(chunks) >= 2
    assert all(" " not in chunk["text"] or len(chunk["text"]) <= 70 for chunk in chunks)
    joined = " ".join(chunk["text"] for chunk in chunks)
    assert "0.8 mmol/mol" in joined
    assert "95%" in joined
    assert "p < 0.001" in joined
    assert all(chunk["section_name"] == "Results" for chunk in chunks)


def test_chunk_deduplicates_identical_passages() -> None:
    chunks = [
        {"text": "Identical evidence.", "section_name": "Methods", "paragraph_number": 1},
        {"text": "Identical evidence.", "section_name": "Methods", "paragraph_number": 2},
    ]
    result = deduplicate_chunks(chunks)
    assert len(result) == 1


def test_html_and_xml_parsing() -> None:
    html = "<html><h2>Results</h2><p>Vitamin D reduced the 25% risk.</p></html>"
    html_passages = parse_html(html)
    assert html_passages
    assert html_passages[0][0] == "Results"
    assert "25%" in html_passages[0][1]

    xml = "<article><section><title>Methods</title><p>We tested 128 participants.</p></section></article>"
    xml_passages = parse_xml(xml)
    assert xml_passages
    assert xml_passages[0][0] == "Methods"
    assert "128 participants" in xml_passages[0][1]


def test_malformed_xml_returns_empty() -> None:
    assert parse_xml("<article><p>broken") == []


def test_pdf_text_extraction() -> None:
    pdf = pymupdf.open()
    page = pdf.new_page()
    page.insert_text((72, 72), "The enzyme activity increased by 12.5 units per minute.")
    data = pdf.tobytes()
    pdf.close()
    pages = extract_pdf_text(data)
    assert len(pages) == 1
    assert "12.5 units" in pages[0][1]


def test_cosine_similarity_and_dimension() -> None:
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_embedding_generation_is_mockable(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeSentenceTransformer:
        def __init__(self, model_name: str) -> None:
            self.model_name = model_name

        def encode(self, texts, batch_size, show_progress_bar):
            assert batch_size == 32
            assert show_progress_bar is False
            return [[0.1] * 384 for _ in texts]

    monkeypatch.setitem(__import__("sys").modules, "sentence_transformers", type(
        "Module",
        (),
        {"SentenceTransformer": FakeSentenceTransformer},
    ))
    vectors = generate_embeddings(["Actual evidence passage"])
    assert len(vectors) == 1
    assert len(vectors[0]) == 384


def test_embedding_dimension_mismatch_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    class WrongSentenceTransformer:
        def __init__(self, model_name: str) -> None:
            pass

        def encode(self, texts, batch_size, show_progress_bar):
            return [[0.1] * 12 for _ in texts]

    monkeypatch.setitem(__import__("sys").modules, "sentence_transformers", type(
        "Module",
        (),
        {"SentenceTransformer": WrongSentenceTransformer},
    ))
    with pytest.raises(RuntimeError, match="dimension mismatch"):
        generate_embeddings(["Evidence"])


def test_evidence_database_persistence_and_duplicate_chunk(evidence_db: Session) -> None:
    user = User(
        email="evidence-owner@example.test",
        full_name="Evidence Owner",
        hashed_password="test",
        is_active=True,
    )
    evidence_db.add(user)
    evidence_db.flush()
    document = Document(
        user_id=user.id,
        title="Evidence document",
        filename="evidence.pdf",
        storage_path="documents/evidence.pdf",
        file_hash="e" * 64,
        file_type="application/pdf",
        file_size=4096,
        processing_status=DocumentStatus.COMPLETED,
    )
    evidence_db.add(document)
    evidence_db.flush()
    version = DocumentVersion(
        document_id=document.id,
        version_number=1,
        storage_key=document.storage_path,
        content_sha256=document.file_hash,
    )
    evidence_db.add(version)
    source = ResearchSource(
        title="Authentic source record",
        doi="10.1234/evidence",
        authors=["A. Researcher"],
        publication_year=2024,
        source_url="https://example.test/article",
        abstract="An authentic abstract was supplied.",
    )
    evidence_db.add(source)
    evidence_db.flush()
    source_version = SourceVersion(
        source_id=source.id,
        content_sha256="f" * 64,
        full_text_available=False,
    )
    evidence_db.add(source_version)
    evidence_db.flush()
    passage = EvidencePassage(
        source_id=source.id,
        source_version_id=source_version.id,
        passage_index=1,
        passage_text="An authentic abstract was supplied.",
        section_name="Abstract",
        content_type="abstract",
        extraction_method="source_metadata_abstract",
        source_url=source.source_url,
        doi=source.doi,
        passage_hash="1" * 64,
    )
    evidence_db.add(passage)
    evidence_db.commit()
    assert evidence_db.query(EvidencePassage).count() == 1
    assert evidence_db.query(EvidencePassage).one().passage_text == "An authentic abstract was supplied."
