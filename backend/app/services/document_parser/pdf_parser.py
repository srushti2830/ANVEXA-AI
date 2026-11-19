"""PDF text extraction using PyMuPDF (fitz).

Extracts text page-by-page, preserving page numbers and collecting
per-page metadata (character count, word count, dimensions).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import pymupdf

logger = logging.getLogger(__name__)


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


def parse_pdf(data: bytes) -> ParsedDocument:
    """Extract text from a PDF file provided as raw bytes.

    Args:
        data: Raw PDF file bytes.

    Returns:
        ParsedDocument with per-page text and metadata.

    Raises:
        ValueError: If the data cannot be parsed as a valid PDF.
    """
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:
        logger.error("Failed to open PDF: %s", exc)
        raise ValueError(f"Cannot parse PDF: {exc}") from exc

    pages: list[ParsedPage] = []
    doc_metadata: dict[str, object] = {}

    # Extract document-level metadata
    pdf_meta = doc.metadata or {}
    for key in ("title", "author", "subject", "keywords", "creator", "producer"):
        value = pdf_meta.get(key)
        if value and str(value).strip():
            doc_metadata[key] = str(value).strip()

    total_pages = len(doc)
    doc_metadata["total_pages"] = total_pages

    for page_idx in range(total_pages):
        page = doc[page_idx]
        page_number = page_idx + 1  # 1-indexed

        # Extract text — use "text" mode for clean plaintext
        text = page.get_text("text").strip()

        # Collect page-level metadata
        rect = page.rect
        page_meta: dict[str, object] = {
            "char_count": len(text),
            "word_count": len(text.split()) if text else 0,
            "width_pt": round(rect.width, 2),
            "height_pt": round(rect.height, 2),
            "has_images": len(page.get_images(full=True)) > 0,
        }

        pages.append(ParsedPage(
            page_number=page_number,
            text=text,
            metadata=page_meta,
        ))

    doc.close()

    logger.info(
        "PDF parsed: %d pages, %d total chars",
        total_pages,
        sum(len(p.text) for p in pages),
    )

    return ParsedDocument(
        pages=pages,
        total_pages=total_pages,
        metadata=doc_metadata,
    )
