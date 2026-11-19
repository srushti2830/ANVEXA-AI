"""Unified document parser — single entry point for all file formats.

Routes to the appropriate parser (PDF or DOCX), optionally invokes
OCR for scanned pages, normalises the output via the text cleaner,
and returns a consistent structured result.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from app.services.document_parser.pdf_parser import parse_pdf
from app.services.document_parser.docx_parser import parse_docx
from app.services.document_parser.ocr_service import (
    TesseractNotFoundError,
    is_tesseract_available,
    run_ocr_on_pages,
)
from app.services.document_parser.text_cleaner import (
    clean_text,
    remove_repeated_headers_footers,
)

logger = logging.getLogger(__name__)

# Supported MIME types
SUPPORTED_MIME_TYPES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
}


@dataclass
class UnifiedParseResult:
    """Consistent structured result from the unified parser."""

    # Document identification
    filename: str
    file_type: str
    extraction_method: str  # "pymupdf", "python-docx", "pymupdf+ocr"

    # Content
    total_pages: int
    extracted_text: str           # full concatenated text
    page_texts: list[dict]        # [{page_number, text, metadata}, ...]
    paragraphs: list[str]         # individual paragraph blocks
    headings: list[dict]          # [{text, level, style}, ...]

    # OCR info
    ocr_pages: list[int]          # page numbers processed through OCR
    ocr_applied: bool

    # Statistics
    character_count: int
    word_count: int
    processing_duration_ms: int

    # Status
    status: str                   # "completed", "completed_with_warnings", "failed"
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    # Metadata from the parser
    metadata: dict[str, object] = field(default_factory=dict)


def parse_document(
    data: bytes,
    filename: str,
    file_type: str,
    enable_ocr: bool = True,
) -> UnifiedParseResult:
    """Parse a document and return a unified structured result.

    Args:
        data: Raw file bytes.
        filename: Original filename.
        file_type: MIME type of the document.
        enable_ocr: Whether to run OCR on scanned PDF pages.

    Returns:
        UnifiedParseResult with text, pages, headings, and metadata.

    Raises:
        ValueError: If the document cannot be parsed.
    """
    start_time = time.monotonic()
    warnings: list[str] = []
    errors: list[str] = []
    ocr_pages: list[int] = []
    ocr_applied = False
    headings: list[dict] = []
    extraction_method = "unknown"

    format_key = SUPPORTED_MIME_TYPES.get(file_type)
    if format_key is None:
        raise ValueError(f"Unsupported file type: {file_type}")

    # --- Route to parser ---
    if format_key == "pdf":
        result = parse_pdf(data)
        extraction_method = "pymupdf"
        warnings.extend(result.warnings)
        ocr_candidates = result.ocr_pages

        # --- OCR for scanned pages ---
        if enable_ocr and ocr_candidates:
            if is_tesseract_available():
                try:
                    ocr_result = run_ocr_on_pages(data, ocr_candidates)
                    warnings.extend(ocr_result.warnings)

                    # Merge OCR text into pages — only replace if OCR gave more text
                    ocr_map = {r.page_number: r for r in ocr_result.pages}
                    merged_pages = []
                    for page in result.pages:
                        if page.page_number in ocr_map:
                            ocr_page = ocr_map[page.page_number]
                            # Only use OCR text if it has more content than the original
                            if len(ocr_page.text) > len(page.text):
                                from app.services.document_parser.pdf_parser import ParsedPage
                                merged_meta = dict(page.metadata)
                                merged_meta["extraction_method"] = "tesseract_ocr"
                                merged_meta["original_char_count"] = page.metadata.get("char_count", 0)
                                if ocr_page.confidence is not None:
                                    merged_meta["ocr_confidence"] = ocr_page.confidence
                                merged_pages.append(ParsedPage(
                                    page_number=page.page_number,
                                    text=ocr_page.text,
                                    metadata=merged_meta,
                                ))
                                ocr_pages.append(page.page_number)
                            else:
                                merged_pages.append(page)
                        else:
                            merged_pages.append(page)

                    # Replace pages with merged version
                    from app.services.document_parser.pdf_parser import ParsedDocument
                    result = ParsedDocument(
                        pages=merged_pages,
                        total_pages=result.total_pages,
                        metadata=result.metadata,
                        ocr_pages=ocr_pages,
                        warnings=result.warnings,
                    )
                    if ocr_pages:
                        ocr_applied = True
                        extraction_method = "pymupdf+ocr"

                except TesseractNotFoundError as exc:
                    warnings.append(str(exc))
                except Exception as exc:
                    logger.error("OCR processing failed: %s", exc)
                    warnings.append(f"OCR processing failed: {exc}")
            else:
                warnings.append(
                    f"Pages {ocr_candidates} may need OCR but Tesseract is not installed. "
                    "Install Tesseract to extract text from scanned pages."
                )

    elif format_key == "docx":
        result = parse_docx(data)
        extraction_method = "python-docx"
        warnings.extend(result.warnings)
        headings = list(result.headings)
    else:
        raise ValueError(f"No parser for format: {format_key}")

    # --- Clean text ---
    page_texts_raw = [p.text for p in result.pages]

    # Remove repeated headers/footers across pages
    page_texts_cleaned = remove_repeated_headers_footers(page_texts_raw)

    # Clean individual pages
    page_texts_final = [clean_text(t) for t in page_texts_cleaned]

    # Build page dicts
    page_dicts: list[dict] = []
    for i, page in enumerate(result.pages):
        cleaned = page_texts_final[i] if i < len(page_texts_final) else page.text
        page_dicts.append({
            "page_number": page.page_number,
            "text": cleaned,
            "metadata": page.metadata,
        })

    # Full text
    full_text = "\n\n".join(page_texts_final)

    # Paragraphs — split by double newlines
    paragraphs = [p.strip() for p in full_text.split("\n\n") if p.strip()]

    # Statistics
    char_count = len(full_text)
    word_count = len(full_text.split()) if full_text else 0

    # Duration
    elapsed_ms = int((time.monotonic() - start_time) * 1000)

    # Status
    if errors:
        parse_status = "failed"
    elif warnings:
        parse_status = "completed_with_warnings"
    else:
        parse_status = "completed"

    # Metadata
    metadata = dict(result.metadata)
    metadata["processing_duration_ms"] = elapsed_ms

    logger.info(
        "Unified parse complete: file=%s type=%s pages=%d chars=%d method=%s duration=%dms",
        filename,
        file_type,
        result.total_pages,
        char_count,
        extraction_method,
        elapsed_ms,
    )

    return UnifiedParseResult(
        filename=filename,
        file_type=file_type,
        extraction_method=extraction_method,
        total_pages=result.total_pages,
        extracted_text=full_text,
        page_texts=page_dicts,
        paragraphs=paragraphs,
        headings=headings,
        ocr_pages=ocr_pages,
        ocr_applied=ocr_applied,
        character_count=char_count,
        word_count=word_count,
        processing_duration_ms=elapsed_ms,
        status=parse_status,
        warnings=warnings,
        errors=errors,
        metadata=metadata,
    )
