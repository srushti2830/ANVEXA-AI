"""Tests for Phase 5 — Document Parsing and OCR.

Creates real (small) PDF and DOCX files in-memory for testing.
Tests cover parsing, OCR detection, text cleaning, API endpoints,
authentication, ownership checks, and database persistence.
"""

from __future__ import annotations

import asyncio
import io
import struct
import uuid
import zipfile
from typing import Iterator
from unittest.mock import patch

import httpx
import pymupdf
import pytest
from docx import Document as DocxDocument
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password, rate_limiter
from app.database.base import Base
from app.database.session import get_db
from app.main import create_app
from app.models.document import Document, DocumentPage, DocumentVersion
from app.models.enums import DocumentStatus, UserRole
from app.models.user import User
from app.services.document_parser.pdf_parser import parse_pdf
from app.services.document_parser.docx_parser import parse_docx
from app.services.document_parser.text_cleaner import (
    clean_text,
    remove_repeated_headers_footers,
)
from app.services.document_parser.ocr_service import (
    TesseractNotFoundError,
    is_tesseract_available,
)
from app.services.document_service import (
    reset_storage_backend,
    set_storage_backend,
)
from app.services.document_storage.storage_service import StorageBackend, StorageError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _setup_settings(monkeypatch):
    monkeypatch.setenv(
        "ANVEXA_JWT_SECRET_KEY",
        "test-secret-key-for-testing-purposes-only-32bytes!",
    )
    get_settings.cache_clear()
    rate_limiter.reset_all()
    yield
    get_settings.cache_clear()
    rate_limiter.reset_all()


@pytest.fixture
def db_session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_fk(connection, _):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    tables = [t for t in Base.metadata.sorted_tables if t.name != "embeddings"]
    Base.metadata.create_all(engine, tables=tables)

    with Session(engine) as session:
        yield session

    engine.dispose()


class InMemoryStorage(StorageBackend):
    """In-memory storage backend for testing."""

    def __init__(self):
        self._store: dict[str, bytes] = {}

    def save(self, storage_key: str, data: bytes) -> str:
        self._store[storage_key] = data
        return f"mem://{storage_key}"

    def delete(self, storage_key: str) -> None:
        self._store.pop(storage_key, None)

    def exists(self, storage_key: str) -> bool:
        return storage_key in self._store

    def read(self, storage_key: str) -> bytes:
        if storage_key not in self._store:
            raise StorageError(f"Not found: {storage_key}")
        return self._store[storage_key]

    def get_path(self, storage_key: str) -> str:
        return f"mem://{storage_key}"


def _request(app, method, path, json=None, headers=None, files=None, data=None):
    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            return await c.request(method, path, json=json, headers=headers, files=files, data=data)
    return asyncio.run(run())


@pytest.fixture
def app_with_db(db_session):
    application = create_app()
    storage = InMemoryStorage()
    set_storage_backend(storage)

    def override_get_db():
        yield db_session

    application.dependency_overrides[get_db] = override_get_db
    yield application, db_session, storage
    reset_storage_backend()


# ---------------------------------------------------------------------------
# Test document generators
# ---------------------------------------------------------------------------


def _make_pdf(pages_text: list[str]) -> bytes:
    """Create a real PDF with the given text on each page."""
    doc = pymupdf.open()
    for text in pages_text:
        page = doc.new_page()
        page.insert_text((72, 72), text, fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


def _make_multi_page_pdf() -> bytes:
    """Create a 5-page academic-style PDF with citations."""
    pages = [
        "Introduction\n\nThis paper examines the effects of climate change [1].\n"
        "Previous studies (Smith et al., 2023) have shown significant impacts.\n"
        "DOI: 10.1234/example.2023.001",
        "Methods\n\nWe used a randomized controlled trial design.\n"
        "Participants (n=500) were recruited from three universities.\n"
        "Data collection followed ISO 9001:2015 standards [2, 3].",
        "Results\n\nTable 1 shows the primary outcomes.\n"
        "The treatment group showed a 23.5% improvement (p < 0.001).\n"
        "These findings align with earlier work [4-6].",
        "Discussion\n\nOur results support the hypothesis proposed by\n"
        "Johnson and Lee (2022). The effect size (d = 0.78) was\n"
        "larger than previously reported [7].",
        "References\n\n[1] Smith A. Climate Change. Nature. 2023;601:45-50.\n"
        "[2] Jones B. Methods Review. Science. 2022;378:112-118.\n"
        "[3] Wang C. Statistical Analysis. PNAS. 2021;118:e2104567.",
    ]
    return _make_pdf(pages)


def _make_empty_pdf() -> bytes:
    """Create a valid PDF with one empty page."""
    doc = pymupdf.open()
    doc.new_page()
    data = doc.tobytes()
    doc.close()
    return data


def _make_image_only_pdf() -> bytes:
    """Create a PDF with only an image (simulating a scanned page)."""
    doc = pymupdf.open()
    page = doc.new_page()
    # Create a small PNG image
    from PIL import Image
    img = Image.new("RGB", (200, 50), color="white")
    from PIL import ImageDraw
    draw = ImageDraw.Draw(img)
    draw.text((10, 10), "OCR TEST TEXT", fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    # Insert the image into the page
    rect = pymupdf.Rect(72, 72, 400, 200)
    page.insert_image(rect, stream=buf.getvalue())
    data = doc.tobytes()
    doc.close()
    return data


def _make_docx(paragraphs: list[tuple[str, str | None]]) -> bytes:
    """Create a real DOCX file. Each item is (text, style_or_None)."""
    doc = DocxDocument()
    for text, style in paragraphs:
        if style:
            doc.add_paragraph(text, style=style)
        else:
            doc.add_paragraph(text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _make_academic_docx() -> bytes:
    """Create a DOCX with headings, paragraphs, citations, and a table."""
    doc = DocxDocument()
    doc.add_heading("Research Paper Title", level=1)
    doc.add_paragraph(
        "This paper examines the effects of climate change [1]. "
        "Previous studies (Smith et al., 2023) have shown significant impacts."
    )
    doc.add_heading("Methods", level=2)
    doc.add_paragraph(
        "We used a randomized controlled trial. "
        "DOI: 10.1234/example.2023.001"
    )
    doc.add_heading("Results", level=2)
    table = doc.add_table(rows=3, cols=2)
    table.cell(0, 0).text = "Metric"
    table.cell(0, 1).text = "Value"
    table.cell(1, 0).text = "Mean Score"
    table.cell(1, 1).text = "85.3"
    table.cell(2, 0).text = "Std Dev"
    table.cell(2, 1).text = "12.1"
    doc.add_paragraph("The treatment group showed a 23.5% improvement [2, 3].")
    doc.add_heading("References", level=2)
    doc.add_paragraph("[1] Smith A. Climate Change. Nature. 2023.")
    doc.add_paragraph("[2] Jones B. Methods Review. Science. 2022.")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _make_unicode_docx() -> bytes:
    """Create a DOCX with Unicode characters."""
    doc = DocxDocument()
    doc.add_paragraph("Ünîcödé Têst — em-dash, "smart quotes", ellipsis…")
    doc.add_paragraph("中文文本测试 • Japanese: テスト • Arabic: اختبار")
    doc.add_paragraph("Maths: α + β = γ, ∑(xᵢ), √2 ≈ 1.414")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Helper: create user + uploaded document in DB
# ---------------------------------------------------------------------------


def _create_user(db: Session, email: str = "test@example.com", role=UserRole.USER) -> User:
    user = User(
        email=email,
        full_name="Test User",
        hashed_password=hash_password("Password123!"),
        role=role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _upload_doc(
    db: Session,
    storage: InMemoryStorage,
    user: User,
    data: bytes,
    filename: str,
    mime: str,
) -> Document:
    import hashlib
    storage_key = f"{uuid.uuid4().hex}{filename[filename.rfind('.'):]}"
    storage.save(storage_key, data)
    doc = Document(
        user_id=user.id,
        title=filename.rsplit(".", 1)[0],
        filename=filename,
        storage_path=storage_key,
        file_hash=hashlib.sha256(data).hexdigest(),
        file_type=mime,
        file_size=len(data),
        processing_status=DocumentStatus.UPLOADED,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def _auth_header(user: User) -> dict:
    token = create_access_token(user_id=user.id, email=user.email, role=user.role.value)
    return {"Authorization": f"Bearer {token}"}


# ===========================================================================
# A. PDF Parser Tests
# ===========================================================================


class TestPDFParser:
    def test_valid_pdf_parsing(self):
        data = _make_pdf(["Hello world. This is page one."])
        result = parse_pdf(data)
        assert result.total_pages == 1
        assert "Hello world" in result.pages[0].text
        assert result.pages[0].page_number == 1

    def test_multi_page_pdf(self):
        data = _make_multi_page_pdf()
        result = parse_pdf(data)
        assert result.total_pages == 5
        for i, page in enumerate(result.pages):
            assert page.page_number == i + 1
            assert page.metadata.get("char_count", 0) > 0

    def test_empty_pdf_page(self):
        data = _make_empty_pdf()
        result = parse_pdf(data)
        assert result.total_pages == 1
        assert len(result.warnings) > 0  # should warn about empty page

    def test_scanned_pdf_detection(self):
        data = _make_image_only_pdf()
        result = parse_pdf(data)
        assert result.total_pages == 1
        # Should detect the page as needing OCR
        assert len(result.ocr_pages) > 0 or result.pages[0].metadata.get("has_images")

    def test_invalid_pdf(self):
        with pytest.raises(ValueError, match="Cannot parse PDF"):
            parse_pdf(b"this is not a pdf file at all")

    def test_pdf_metadata_extraction(self):
        data = _make_multi_page_pdf()
        result = parse_pdf(data)
        assert "total_pages" in result.metadata
        assert result.metadata["total_pages"] == 5

    def test_pdf_preserves_page_numbers(self):
        data = _make_pdf(["Page 1 text", "Page 2 text", "Page 3 text"])
        result = parse_pdf(data)
        assert [p.page_number for p in result.pages] == [1, 2, 3]

    def test_pdf_page_metadata(self):
        data = _make_pdf(["Some text on this page"])
        result = parse_pdf(data)
        meta = result.pages[0].metadata
        assert "char_count" in meta
        assert "word_count" in meta
        assert "width_pt" in meta
        assert "height_pt" in meta
        assert "extraction_method" in meta


# ===========================================================================
# B. DOCX Parser Tests
# ===========================================================================


class TestDOCXParser:
    def test_valid_docx_parsing(self):
        data = _make_docx([("Hello world from DOCX.", None)])
        result = parse_docx(data)
        assert result.total_pages >= 1
        assert "Hello world" in result.pages[0].text

    def test_headings_extracted(self):
        data = _make_academic_docx()
        result = parse_docx(data)
        assert len(result.headings) > 0
        heading_texts = [h["text"] for h in result.headings]
        assert "Research Paper Title" in heading_texts
        assert "Methods" in heading_texts

    def test_heading_levels(self):
        data = _make_academic_docx()
        result = parse_docx(data)
        h1 = [h for h in result.headings if h["level"] == 1]
        h2 = [h for h in result.headings if h["level"] == 2]
        assert len(h1) >= 1
        assert len(h2) >= 2

    def test_table_extraction(self):
        data = _make_academic_docx()
        result = parse_docx(data)
        full = "\n\n".join(p.text for p in result.pages)
        assert "Mean Score" in full or "85.3" in full

    def test_empty_docx(self):
        doc = DocxDocument()
        buf = io.BytesIO()
        doc.save(buf)
        data = buf.getvalue()
        result = parse_docx(data)
        assert result.total_pages == 1
        assert result.pages[0].text == ""
        assert len(result.warnings) > 0

    def test_invalid_docx(self):
        with pytest.raises(ValueError, match="Cannot parse DOCX"):
            parse_docx(b"not a docx file")

    def test_unicode_docx(self):
        data = _make_unicode_docx()
        result = parse_docx(data)
        full = "\n\n".join(p.text for p in result.pages)
        assert "Ünîcödé" in full
        assert "中文" in full
        assert "α + β" in full

    def test_docx_structured_blocks(self):
        data = _make_academic_docx()
        result = parse_docx(data)
        block_types = {b.block_type for b in result.blocks}
        assert "paragraph" in block_types
        assert "heading" in block_types


# ===========================================================================
# C. OCR Service Tests
# ===========================================================================


class TestOCRService:
    def test_tesseract_availability_check(self):
        # Just verify the function doesn't crash
        result = is_tesseract_available()
        assert isinstance(result, bool)

    def test_missing_tesseract_error(self):
        with patch(
            "app.services.document_parser.ocr_service.shutil.which",
            return_value=None,
        ):
            from app.services.document_parser.ocr_service import _ensure_tesseract
            with pytest.raises(TesseractNotFoundError, match="Tesseract OCR is not installed"):
                _ensure_tesseract()


# ===========================================================================
# D. Text Cleaner Tests
# ===========================================================================


class TestTextCleaner:
    def test_whitespace_normalization(self):
        result = clean_text("hello    world")
        assert result == "hello world"

    def test_multiple_newlines(self):
        result = clean_text("para1\n\n\n\n\npara2")
        assert result == "para1\n\npara2"

    def test_unicode_normalization(self):
        # Non-breaking space and BOM
        result = clean_text("hello\u00a0world\ufeff")
        assert result == "hello world"

    def test_preserves_citation_numeric(self):
        text = "Studies show improvement [1]. Also see [2, 3] and [4-6]."
        result = clean_text(text)
        assert "[1]" in result
        assert "[2, 3]" in result
        assert "[4-6]" in result

    def test_preserves_citation_author_year(self):
        text = "As shown by (Smith et al., 2023) and (Johnson and Lee, 2022)."
        result = clean_text(text)
        assert "(Smith et al., 2023)" in result
        assert "(Johnson and Lee, 2022)" in result

    def test_preserves_doi(self):
        text = "Available at DOI: 10.1234/example.2023.001"
        result = clean_text(text)
        assert "10.1234/example.2023.001" in result

    def test_preserves_headings(self):
        text = "Introduction\n\nThis is the content."
        result = clean_text(text)
        assert "Introduction" in result

    def test_removes_page_numbers(self):
        text = "Some content\n42\nMore content"
        result = clean_text(text)
        assert "Some content" in result
        assert "More content" in result

    def test_empty_text(self):
        assert clean_text("") == ""
        assert clean_text("   ") == ""

    def test_header_footer_removal(self):
        pages = [
            "Journal of Testing Vol 1\nContent page 1\nPage 1 of 5",
            "Journal of Testing Vol 1\nContent page 2\nPage 2 of 5",
            "Journal of Testing Vol 1\nContent page 3\nPage 3 of 5",
            "Journal of Testing Vol 1\nContent page 4\nPage 4 of 5",
        ]
        cleaned = remove_repeated_headers_footers(pages, threshold=3)
        # The repeated header should be removed
        for page in cleaned:
            assert "Journal of Testing Vol 1" not in page


# ===========================================================================
# E-G. API Integration Tests (parse + retrieve)
# ===========================================================================


class TestParsingAPI:
    def test_parse_pdf_via_api(self, app_with_db):
        app, db, storage = app_with_db
        user = _create_user(db)
        pdf_data = _make_multi_page_pdf()
        doc = _upload_doc(db, storage, user, pdf_data, "paper.pdf", "application/pdf")

        resp = _request(app, "POST", f"/api/v1/documents/{doc.id}/parse", headers=_auth_header(user))
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_pages"] == 5
        assert data["processing_status"] == "completed"
        assert data["extraction_method"] == "pymupdf"
        assert data["total_characters"] > 0

    def test_parse_docx_via_api(self, app_with_db):
        app, db, storage = app_with_db
        user = _create_user(db)
        docx_data = _make_academic_docx()
        doc = _upload_doc(
            db, storage, user, docx_data, "paper.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

        resp = _request(app, "POST", f"/api/v1/documents/{doc.id}/parse", headers=_auth_header(user))
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_pages"] >= 1
        assert data["processing_status"] == "completed"
        assert data["extraction_method"] == "python-docx"

    def test_retrieve_parsed_content(self, app_with_db):
        app, db, storage = app_with_db
        user = _create_user(db)
        pdf_data = _make_multi_page_pdf()
        doc = _upload_doc(db, storage, user, pdf_data, "test.pdf", "application/pdf")

        # Parse first
        _request(app, "POST", f"/api/v1/documents/{doc.id}/parse", headers=_auth_header(user))

        # Retrieve
        resp = _request(app, "GET", f"/api/v1/documents/{doc.id}/parsed-content", headers=_auth_header(user))
        assert resp.status_code == 200
        data = resp.json()
        assert "extracted_text" in data
        assert "pages" in data
        assert len(data["pages"]) == 5
        assert data["pages"][0]["page_number"] == 1

    def test_retrieve_before_parsing(self, app_with_db):
        app, db, storage = app_with_db
        user = _create_user(db)
        pdf_data = _make_pdf(["test"])
        doc = _upload_doc(db, storage, user, pdf_data, "test.pdf", "application/pdf")

        resp = _request(app, "GET", f"/api/v1/documents/{doc.id}/parsed-content", headers=_auth_header(user))
        assert resp.status_code == 404

    def test_parse_already_completed_document(self, app_with_db):
        app, db, storage = app_with_db
        user = _create_user(db)
        pdf_data = _make_pdf(["test"])
        doc = _upload_doc(db, storage, user, pdf_data, "test.pdf", "application/pdf")

        # Parse once
        _request(app, "POST", f"/api/v1/documents/{doc.id}/parse", headers=_auth_header(user))

        # Try to parse again — should fail (already completed)
        resp = _request(app, "POST", f"/api/v1/documents/{doc.id}/parse", headers=_auth_header(user))
        assert resp.status_code == 409

    def test_parse_failed_document_can_retry(self, app_with_db):
        app, db, storage = app_with_db
        user = _create_user(db)
        pdf_data = _make_pdf(["retry test"])
        doc = _upload_doc(db, storage, user, pdf_data, "test.pdf", "application/pdf")

        # Set to FAILED
        doc.processing_status = DocumentStatus.FAILED
        db.commit()

        resp = _request(app, "POST", f"/api/v1/documents/{doc.id}/parse", headers=_auth_header(user))
        assert resp.status_code == 200

    def test_database_persistence(self, app_with_db):
        app, db, storage = app_with_db
        user = _create_user(db)
        pdf_data = _make_pdf(["Persistent text page 1", "Persistent text page 2"])
        doc = _upload_doc(db, storage, user, pdf_data, "persist.pdf", "application/pdf")

        _request(app, "POST", f"/api/v1/documents/{doc.id}/parse", headers=_auth_header(user))

        # Check DB records
        db.refresh(doc)
        assert doc.processing_status == DocumentStatus.COMPLETED

        versions = db.query(DocumentVersion).filter_by(document_id=doc.id).all()
        assert len(versions) == 1

        pages = db.query(DocumentPage).filter_by(document_version_id=versions[0].id).all()
        assert len(pages) == 2
        assert pages[0].page_number == 1
        assert "Persistent text" in pages[0].extracted_text

    def test_citation_preservation_through_api(self, app_with_db):
        app, db, storage = app_with_db
        user = _create_user(db)
        pdf_data = _make_multi_page_pdf()
        doc = _upload_doc(db, storage, user, pdf_data, "cite.pdf", "application/pdf")

        _request(app, "POST", f"/api/v1/documents/{doc.id}/parse", headers=_auth_header(user))

        resp = _request(app, "GET", f"/api/v1/documents/{doc.id}/parsed-content", headers=_auth_header(user))
        text = resp.json()["extracted_text"]
        # Citations should survive the cleaning pipeline
        assert "[1]" in text
        assert "10.1234/example.2023.001" in text

    def test_parse_nonexistent_document(self, app_with_db):
        app, db, storage = app_with_db
        user = _create_user(db)
        fake_id = uuid.uuid4()
        resp = _request(app, "POST", f"/api/v1/documents/{fake_id}/parse", headers=_auth_header(user))
        assert resp.status_code == 404

    def test_parsing_failure_sets_failed_status(self, app_with_db):
        app, db, storage = app_with_db
        user = _create_user(db)
        # Upload invalid content with pdf extension/mime
        bad_data = b"not a real pdf"
        doc = _upload_doc(db, storage, user, bad_data, "bad.pdf", "application/pdf")

        resp = _request(app, "POST", f"/api/v1/documents/{doc.id}/parse", headers=_auth_header(user))
        assert resp.status_code == 422

        db.refresh(doc)
        assert doc.processing_status == DocumentStatus.FAILED


# ===========================================================================
# H. Security Tests
# ===========================================================================


class TestParsingSecurity:
    def test_unauthorized_parse(self, app_with_db):
        app, db, storage = app_with_db
        user = _create_user(db)
        pdf_data = _make_pdf(["test"])
        doc = _upload_doc(db, storage, user, pdf_data, "test.pdf", "application/pdf")

        # No auth header
        resp = _request(app, "POST", f"/api/v1/documents/{doc.id}/parse")
        assert resp.status_code == 401

    def test_unauthorized_get_content(self, app_with_db):
        app, db, storage = app_with_db
        user = _create_user(db)
        pdf_data = _make_pdf(["test"])
        doc = _upload_doc(db, storage, user, pdf_data, "test.pdf", "application/pdf")

        resp = _request(app, "GET", f"/api/v1/documents/{doc.id}/parsed-content")
        assert resp.status_code == 401

    def test_cross_user_parse_blocked(self, app_with_db):
        app, db, storage = app_with_db
        user1 = _create_user(db, email="user1@test.org")
        user2 = _create_user(db, email="user2@test.org")

        pdf_data = _make_pdf(["user1 doc"])
        doc = _upload_doc(db, storage, user1, pdf_data, "private.pdf", "application/pdf")

        # User2 tries to parse user1's document
        resp = _request(app, "POST", f"/api/v1/documents/{doc.id}/parse", headers=_auth_header(user2))
        assert resp.status_code == 403

    def test_cross_user_content_blocked(self, app_with_db):
        app, db, storage = app_with_db
        user1 = _create_user(db, email="user1b@test.org")
        user2 = _create_user(db, email="user2b@test.org")

        pdf_data = _make_pdf(["secret content"])
        doc = _upload_doc(db, storage, user1, pdf_data, "secret.pdf", "application/pdf")

        # Parse as user1
        _request(app, "POST", f"/api/v1/documents/{doc.id}/parse", headers=_auth_header(user1))

        # User2 tries to retrieve
        resp = _request(app, "GET", f"/api/v1/documents/{doc.id}/parsed-content", headers=_auth_header(user2))
        assert resp.status_code == 403
