"""PDF text extraction using PyMuPDF.

Extracts text page-by-page, preserves page numbers and paragraph breaks,
detects scanned/image-based pages, handles corrupted and encrypted PDFs,
and collects per-page metadata.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import pymupdf

logger = logging.getLogger(__name__)

# Pages with fewer extractable characters than this are considered
# "low-text" and flagged as potential OCR candidates.
_LOW_TEXT_THRESHOLD = 50


@dataclass(frozen=True)
class ParsedPage:
    """Represents the extracted content of a single document page."""

    page_number: int
    text: str
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ParsedDocument:
    """Full extraction result for a document."""

    pages: list[ParsedPage]
    total_pages: int
    metadata: dict[str, object] = field(default_factory=dict)
    ocr_pages: list[int] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _is_scanned_page(page: pymupdf.Page, text: str) -> bool:
    """Heuristic: a page is likely scanned if it has images but very little text."""
    has_images = len(page.get_images(full=True)) > 0
    low_text = len(text.strip()) < _LOW_TEXT_THRESHOLD
    return has_images and low_text


def parse_pdf(data: bytes) -> ParsedDocument:
    """Extract text from a PDF file provided as raw bytes.

    Args:
        data: Raw PDF file bytes.

    Returns:
        ParsedDocument with per-page text and metadata.

    Raises:
        ValueError: If the data cannot be parsed as a valid PDF.
    """
    warnings: list[str] = []

    # --- Open document ---
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:
        logger.error("Failed to open PDF: %s", exc)
        raise ValueError(f"Cannot parse PDF: {exc}") from exc

    # --- Encrypted PDF handling ---
    if doc.is_encrypted:
        # Try opening with empty password (many PDFs have print-only restrictions)
        if not doc.authenticate(""):
            doc.close()
            raise ValueError(
                "PDF is encrypted and requires a password. "
                "Cannot extract text from password-protected documents."
            )
        warnings.append("PDF was encrypted; opened with empty password.")

    total_pages = len(doc)
    if total_pages == 0:
        doc.close()
        raise ValueError("PDF contains no pages.")

    # --- Document-level metadata ---
    doc_metadata: dict[str, object] = {}
    pdf_meta = doc.metadata or {}
    for key in ("title", "author", "subject", "keywords", "creator", "producer"):
        value = pdf_meta.get(key)
        if value and str(value).strip():
            doc_metadata[key] = str(value).strip()
    doc_metadata["total_pages"] = total_pages
    doc_metadata["is_encrypted"] = doc.is_encrypted

    # --- Extract text page-by-page ---
    pages: list[ParsedPage] = []
    ocr_pages: list[int] = []
    empty_pages: list[int] = []

    for page_idx in range(total_pages):
        page = doc[page_idx]
        page_number = page_idx + 1  # 1-indexed

        # Extract text — "text" mode gives clean plaintext with paragraph breaks
        try:
            text = page.get_text("text")
        except Exception as exc:
            logger.warning(
                "Text extraction failed for page %d: %s", page_number, exc
            )
            text = ""
            warnings.append(f"Page {page_number}: text extraction failed ({exc})")

        text_stripped = text.strip()

        # Detect scanned/image pages
        is_scanned = _is_scanned_page(page, text_stripped)
        needs_ocr = is_scanned
        has_images = len(page.get_images(full=True)) > 0

        if needs_ocr:
            ocr_pages.append(page_number)

        if not text_stripped:
            empty_pages.append(page_number)

        # Collect page-level metadata
        rect = page.rect
        page_meta: dict[str, object] = {
            "char_count": len(text_stripped),
            "word_count": len(text_stripped.split()) if text_stripped else 0,
            "width_pt": round(rect.width, 2),
            "height_pt": round(rect.height, 2),
            "has_images": has_images,
            "needs_ocr": needs_ocr,
            "extraction_method": "pymupdf",
        }

        pages.append(ParsedPage(
            page_number=page_number,
            text=text_stripped,
            metadata=page_meta,
        ))

    doc.close()

    # --- Warnings for quality issues ---
    if empty_pages:
        warnings.append(
            f"Pages with no extractable text: {empty_pages}"
        )
    if ocr_pages:
        warnings.append(
            f"Pages that may be scanned and need OCR: {ocr_pages}"
        )

    total_chars = sum(len(p.text) for p in pages)
    if total_chars == 0:
        warnings.append(
            "No text was extracted from any page. "
            "The PDF may be entirely image-based and require OCR."
        )

    doc_metadata["extraction_method"] = "pymupdf"
    doc_metadata["ocr_page_count"] = len(ocr_pages)
    doc_metadata["empty_page_count"] = len(empty_pages)
    doc_metadata["total_characters"] = total_chars

    logger.info(
        "PDF parsed: %d pages, %d chars, %d OCR candidates",
        total_pages,
        total_chars,
        len(ocr_pages),
    )

    return ParsedDocument(
        pages=pages,
        total_pages=total_pages,
        metadata=doc_metadata,
        ocr_pages=ocr_pages,
        warnings=warnings,
    )
