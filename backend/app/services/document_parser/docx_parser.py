"""DOCX text extraction using python-docx.

Extracts paragraphs (with heading levels), tables, and document
metadata.  Since DOCX files lack physical page boundaries, text is
segmented into logical "pages" using a character-count threshold.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field

from docx import Document as DocxDocument
from docx.opc.exceptions import PackageNotFoundError

logger = logging.getLogger(__name__)

# Approximate characters per logical "page"
_CHARS_PER_PAGE = 3000


@dataclass(frozen=True)
class TextBlock:
    """A single paragraph or table block extracted from a DOCX."""

    text: str
    block_type: str  # "paragraph", "heading", "table"
    heading_level: int | None = None  # 1–9 for headings, None otherwise


@dataclass(frozen=True)
class ParsedPage:
    """Extracted content of a single logical page."""

    page_number: int
    text: str
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ParsedDocument:
    """Full extraction result for a document."""

    pages: list[ParsedPage]
    total_pages: int
    metadata: dict[str, object] = field(default_factory=dict)
    blocks: list[TextBlock] = field(default_factory=list)
    headings: list[dict[str, object]] = field(default_factory=list)
    ocr_pages: list[int] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _extract_table_text(table) -> str:
    """Extract text from a docx Table, joining cells with tabs and rows with newlines."""
    rows: list[str] = []
    for row in table.rows:
        cells = [cell.text.strip() for cell in row.cells]
        rows.append("\t".join(cells))
    return "\n".join(rows)


def _heading_level(style_name: str | None) -> int | None:
    """Return heading level (1-9) if the style is a heading, else None."""
    if not style_name:
        return None
    name = style_name.strip()
    # python-docx heading styles: "Heading 1", "Heading 2", ...
    if name.lower().startswith("heading "):
        try:
            return int(name.split()[-1])
        except (ValueError, IndexError):
            return None
    return None


def parse_docx(data: bytes) -> ParsedDocument:
    """Extract text from a DOCX file provided as raw bytes.

    Args:
        data: Raw DOCX file bytes.

    Returns:
        ParsedDocument with logical pages, blocks, headings, and metadata.

    Raises:
        ValueError: If the data cannot be parsed as a valid DOCX.
    """
    warnings: list[str] = []

    try:
        doc = DocxDocument(io.BytesIO(data))
    except PackageNotFoundError as exc:
        raise ValueError(f"Cannot parse DOCX: file is corrupted or not a valid DOCX ({exc})") from exc
    except Exception as exc:
        logger.error("Failed to open DOCX: %s", exc)
        raise ValueError(f"Cannot parse DOCX: {exc}") from exc

    # --- Collect structured blocks ---
    blocks: list[TextBlock] = []
    headings: list[dict[str, object]] = []

    for paragraph in doc.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue

        style_name = paragraph.style.name if paragraph.style else None
        level = _heading_level(style_name)

        if level is not None:
            blocks.append(TextBlock(
                text=text,
                block_type="heading",
                heading_level=level,
            ))
            headings.append({
                "text": text,
                "level": level,
                "style": style_name,
            })
        else:
            blocks.append(TextBlock(text=text, block_type="paragraph"))

    for table in doc.tables:
        table_text = _extract_table_text(table)
        if table_text.strip():
            blocks.append(TextBlock(text=table_text, block_type="table"))

    # --- Document-level metadata ---
    doc_metadata: dict[str, object] = {}
    try:
        core = doc.core_properties
        if core.title:
            doc_metadata["title"] = core.title
        if core.author:
            doc_metadata["author"] = core.author
        if core.subject:
            doc_metadata["subject"] = core.subject
        if core.keywords:
            doc_metadata["keywords"] = core.keywords
    except Exception:
        pass  # core properties may be absent or malformed

    full_text = "\n\n".join(b.text for b in blocks)
    doc_metadata["paragraph_count"] = sum(1 for b in blocks if b.block_type == "paragraph")
    doc_metadata["heading_count"] = len(headings)
    doc_metadata["table_count"] = sum(1 for b in blocks if b.block_type == "table")
    doc_metadata["total_chars"] = len(full_text)
    doc_metadata["extraction_method"] = "python-docx"

    if not blocks:
        warnings.append("DOCX contains no extractable text.")

    # --- Segment into logical pages ---
    pages: list[ParsedPage] = []
    if blocks:
        current_text: list[str] = []
        current_len = 0
        page_num = 1

        for block in blocks:
            current_text.append(block.text)
            current_len += len(block.text) + 2

            if current_len >= _CHARS_PER_PAGE:
                page_text = "\n\n".join(current_text)
                pages.append(ParsedPage(
                    page_number=page_num,
                    text=page_text,
                    metadata={
                        "char_count": len(page_text),
                        "word_count": len(page_text.split()),
                        "extraction_method": "python-docx",
                    },
                ))
                page_num += 1
                current_text = []
                current_len = 0

        if current_text:
            page_text = "\n\n".join(current_text)
            pages.append(ParsedPage(
                page_number=page_num,
                text=page_text,
                metadata={
                    "char_count": len(page_text),
                    "word_count": len(page_text.split()),
                    "extraction_method": "python-docx",
                },
            ))
    else:
        pages.append(ParsedPage(
            page_number=1,
            text="",
            metadata={"char_count": 0, "word_count": 0, "extraction_method": "python-docx"},
        ))

    total_pages = len(pages)
    doc_metadata["total_pages"] = total_pages

    logger.info(
        "DOCX parsed: %d logical pages, %d blocks, %d chars",
        total_pages,
        len(blocks),
        len(full_text),
    )

    return ParsedDocument(
        pages=pages,
        total_pages=total_pages,
        metadata=doc_metadata,
        blocks=blocks,
        headings=headings,
        ocr_pages=[],
        warnings=warnings,
    )
