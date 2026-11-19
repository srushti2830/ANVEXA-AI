"""DOCX text extraction using python-docx.

DOCX files lack physical page boundaries.  This module extracts all
paragraphs and tables, then segments them into logical "pages" using
a configurable character-count threshold to maintain a consistent
page-based data model.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from docx import Document as DocxDocument
from docx.opc.exceptions import PackageNotFoundError

logger = logging.getLogger(__name__)

# Approximate characters per logical "page" for DOCX segmentation
_CHARS_PER_PAGE = 3000


@dataclass(frozen=True)
class ParsedPage:
    """Represents extracted content of a single logical page."""

    page_number: int
    text: str
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ParsedDocument:
    """Full extraction result for a document."""

    pages: list[ParsedPage]
    total_pages: int
    metadata: dict[str, object] = field(default_factory=dict)


def _extract_table_text(table) -> str:
    """Extract text from a docx Table, joining cells with tabs and rows with newlines."""
    rows: list[str] = []
    for row in table.rows:
        cells = [cell.text.strip() for cell in row.cells]
        rows.append("\t".join(cells))
    return "\n".join(rows)


def parse_docx(data: bytes) -> ParsedDocument:
    """Extract text from a DOCX file provided as raw bytes.

    Paragraphs and tables are read in document order and segmented
    into logical pages of approximately ``_CHARS_PER_PAGE`` characters.

    Args:
        data: Raw DOCX file bytes.

    Returns:
        ParsedDocument with logical pages and metadata.

    Raises:
        ValueError: If the data cannot be parsed as a valid DOCX.
    """
    import io

    try:
        doc = DocxDocument(io.BytesIO(data))
    except (PackageNotFoundError, Exception) as exc:
        logger.error("Failed to open DOCX: %s", exc)
        raise ValueError(f"Cannot parse DOCX: {exc}") from exc

    # Collect all text blocks in document order
    # (paragraphs and tables interleaved)
    blocks: list[str] = []
    for element in doc.element.body:
        tag = element.tag.split("}")[-1] if "}" in element.tag else element.tag
        if tag == "p":
            # Paragraph
            text = element.text or ""
            # For proper extraction, walk all runs
            from docx.oxml.ns import qn

            runs_text = []
            for run_el in element.iter(qn("w:t")):
                runs_text.append(run_el.text or "")
            paragraph_text = "".join(runs_text).strip()
            if paragraph_text:
                blocks.append(paragraph_text)
        elif tag == "tbl":
            # Table — use python-docx Table wrapper
            from docx.table import Table

            table = Table(element, doc)
            table_text = _extract_table_text(table)
            if table_text.strip():
                blocks.append(table_text)

    full_text = "\n\n".join(blocks)

    # Document-level metadata
    core_props = doc.core_properties
    doc_metadata: dict[str, object] = {}
    if core_props.title:
        doc_metadata["title"] = core_props.title
    if core_props.author:
        doc_metadata["author"] = core_props.author
    if core_props.subject:
        doc_metadata["subject"] = core_props.subject
    if core_props.keywords:
        doc_metadata["keywords"] = core_props.keywords

    doc_metadata["paragraph_count"] = len(blocks)
    doc_metadata["total_chars"] = len(full_text)

    # Segment into logical pages
    pages: list[ParsedPage] = []
    if full_text:
        # Split by blocks, accumulate until we hit the threshold
        current_text: list[str] = []
        current_len = 0
        page_num = 1

        for block in blocks:
            current_text.append(block)
            current_len += len(block) + 2  # +2 for "\n\n" join

            if current_len >= _CHARS_PER_PAGE:
                page_text = "\n\n".join(current_text)
                pages.append(ParsedPage(
                    page_number=page_num,
                    text=page_text,
                    metadata={
                        "char_count": len(page_text),
                        "word_count": len(page_text.split()),
                    },
                ))
                page_num += 1
                current_text = []
                current_len = 0

        # Remaining text becomes the last page
        if current_text:
            page_text = "\n\n".join(current_text)
            pages.append(ParsedPage(
                page_number=page_num,
                text=page_text,
                metadata={
                    "char_count": len(page_text),
                    "word_count": len(page_text.split()),
                },
            ))
    else:
        # Empty document — single empty page
        pages.append(ParsedPage(
            page_number=1,
            text="",
            metadata={"char_count": 0, "word_count": 0},
        ))

    total_pages = len(pages)
    doc_metadata["total_pages"] = total_pages

    logger.info(
        "DOCX parsed: %d logical pages, %d total chars",
        total_pages,
        len(full_text),
    )

    return ParsedDocument(
        pages=pages,
        total_pages=total_pages,
        metadata=doc_metadata,
    )
