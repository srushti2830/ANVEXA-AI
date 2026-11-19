"""OCR service using Tesseract OCR with PyMuPDF page rendering.

Detects pages needing OCR, renders them to images via PyMuPDF, then
runs Tesseract via pytesseract to extract text.  Never silently
replaces valid extracted text with poor OCR output.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field

import pymupdf

logger = logging.getLogger(__name__)

# DPI used to rasterise PDF pages for OCR
_OCR_DPI = 300

# Minimum characters for OCR output to be considered useful
_OCR_MIN_CHARS = 20


class TesseractNotFoundError(RuntimeError):
    """Raised when Tesseract OCR binary cannot be found."""


@dataclass(frozen=True)
class OCRPageResult:
    """Result of OCR processing for a single page."""

    page_number: int
    text: str
    confidence: float | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class OCRResult:
    """Aggregate result of OCR processing for a document."""

    pages: list[OCRPageResult]
    ocr_page_numbers: list[int]
    warnings: list[str] = field(default_factory=list)


def is_tesseract_available() -> bool:
    """Check if Tesseract OCR binary is available on the system PATH."""
    return shutil.which("tesseract") is not None


def _ensure_tesseract() -> None:
    """Raise a clear error if Tesseract is not installed."""
    if not is_tesseract_available():
        raise TesseractNotFoundError(
            "Tesseract OCR is not installed or not on PATH. "
            "Install it from https://github.com/UB-Mannheim/tesseract/wiki "
            "(Windows) or via your system package manager. "
            "After installation, ensure 'tesseract' is accessible from the command line."
        )


def run_ocr_on_pages(
    pdf_data: bytes,
    page_numbers: list[int],
) -> OCRResult:
    """Run OCR on specified pages of a PDF.

    Args:
        pdf_data: Raw PDF bytes.
        page_numbers: 1-indexed page numbers to OCR.

    Returns:
        OCRResult with per-page extracted text and metadata.

    Raises:
        TesseractNotFoundError: If Tesseract is not installed.
        ValueError: If the PDF cannot be opened.
    """
    _ensure_tesseract()

    # Lazy imports so the module loads even without tesseract/Pillow
    import pytesseract
    from PIL import Image
    import io

    warnings: list[str] = []
    results: list[OCRPageResult] = []

    try:
        doc = pymupdf.open(stream=pdf_data, filetype="pdf")
    except Exception as exc:
        raise ValueError(f"Cannot open PDF for OCR: {exc}") from exc

    total_pages = len(doc)

    for page_num in page_numbers:
        if page_num < 1 or page_num > total_pages:
            warnings.append(f"Page {page_num} is out of range (1-{total_pages}), skipped.")
            continue

        page = doc[page_num - 1]  # 0-indexed

        # Render page to a pixmap at OCR_DPI
        try:
            zoom = _OCR_DPI / 72  # 72 is the default PDF DPI
            matrix = pymupdf.Matrix(zoom, zoom)
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)

            # Convert to PIL Image
            img = Image.open(io.BytesIO(pixmap.tobytes("png")))

            # Run Tesseract
            ocr_text = pytesseract.image_to_string(img, lang="eng")
            ocr_text = ocr_text.strip()

            # Confidence data (optional)
            try:
                ocr_data = pytesseract.image_to_data(
                    img, lang="eng", output_type=pytesseract.Output.DICT
                )
                confidences = [
                    int(c) for c in ocr_data.get("conf", [])
                    if str(c).isdigit() and int(c) >= 0
                ]
                avg_confidence = (
                    sum(confidences) / len(confidences) if confidences else None
                )
            except Exception:
                avg_confidence = None

            page_meta: dict[str, object] = {
                "extraction_method": "tesseract_ocr",
                "ocr_dpi": _OCR_DPI,
                "char_count": len(ocr_text),
                "word_count": len(ocr_text.split()) if ocr_text else 0,
            }
            if avg_confidence is not None:
                page_meta["ocr_confidence"] = round(avg_confidence, 1)

            if len(ocr_text) < _OCR_MIN_CHARS:
                warnings.append(
                    f"Page {page_num}: OCR produced very little text "
                    f"({len(ocr_text)} chars). The page may be blank or "
                    f"contain non-textual content."
                )

            results.append(OCRPageResult(
                page_number=page_num,
                text=ocr_text,
                confidence=avg_confidence,
                metadata=page_meta,
            ))

        except Exception as exc:
            logger.error("OCR failed for page %d: %s", page_num, exc)
            warnings.append(f"Page {page_num}: OCR processing failed ({exc})")
            results.append(OCRPageResult(
                page_number=page_num,
                text="",
                metadata={"extraction_method": "tesseract_ocr", "error": str(exc)},
            ))

    doc.close()

    logger.info(
        "OCR completed: %d/%d pages processed, %d total chars",
        len(results),
        len(page_numbers),
        sum(len(r.text) for r in results),
    )

    return OCRResult(
        pages=results,
        ocr_page_numbers=[r.page_number for r in results],
        warnings=warnings,
    )
