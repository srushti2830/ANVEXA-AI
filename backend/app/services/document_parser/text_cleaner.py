"""Text cleaner for parsed document content.

Normalises whitespace, reduces header/footer noise, applies Unicode
normalisation, and preserves meaningful content such as citation
markers, DOIs, section headings, and punctuation.
"""

from __future__ import annotations

import re
import unicodedata


# ---------------------------------------------------------------------------
# Compiled patterns
# ---------------------------------------------------------------------------

# Citation markers we must NOT remove
_CITATION_NUMERIC = re.compile(r"\[\d+(?:[-–,\s]*\d+)*\]")  # [1], [1-3], [1, 2]
_CITATION_AUTHOR_YEAR = re.compile(
    r"\([A-Z][a-zA-Zà-ÿ'-]+(?:\s+(?:et\s+al\.?|and|&)\s*[A-Z][a-zA-Zà-ÿ'-]+)*"
    r"[,;]?\s*\d{4}[a-z]?\)"
)
_DOI_PATTERN = re.compile(r"10\.\d{4,}/[^\s]+")

# Whitespace patterns
_MULTIPLE_SPACES = re.compile(r"[^\S\n]{2,}")  # 2+ non-newline spaces
_MULTIPLE_NEWLINES = re.compile(r"\n{3,}")      # 3+ consecutive newlines
_TRAILING_SPACES = re.compile(r" +\n")          # spaces before newline

# Common header/footer noise patterns
_PAGE_NUMBER_LINE = re.compile(
    r"^(?:\s*[-–—]\s*)?\d{1,4}(?:\s*[-–—]\s*)?$", re.MULTILINE
)
_REPEATED_LINE_THRESHOLD = 3  # lines appearing this many times are likely headers/footers


def clean_text(text: str) -> str:
    """Apply a sequence of cleaning operations to extracted text.

    The cleaner preserves:
    - Citation markers: [1], (Smith et al., 2023), etc.
    - DOI strings: 10.xxxx/...
    - Section headings and meaningful punctuation
    - Paragraph boundaries (single blank lines)

    Args:
        text: Raw extracted text.

    Returns:
        Cleaned text with normalised whitespace and reduced noise.
    """
    if not text:
        return ""

    # 1. Unicode normalisation (NFC — compose characters)
    result = unicodedata.normalize("NFC", text)

    # 2. Replace common Unicode whitespace variants with ASCII equivalents
    result = result.replace("\u00a0", " ")   # non-breaking space
    result = result.replace("\u200b", "")    # zero-width space
    result = result.replace("\ufeff", "")    # BOM
    result = result.replace("\u2028", "\n")  # line separator
    result = result.replace("\u2029", "\n")  # paragraph separator

    # 3. Normalise tabs to spaces within lines
    result = result.replace("\t", "    ")

    # 4. Collapse multiple spaces (not newlines) into single space
    result = _MULTIPLE_SPACES.sub(" ", result)

    # 5. Remove trailing spaces on each line
    result = _TRAILING_SPACES.sub("\n", result)

    # 6. Collapse 3+ consecutive newlines into 2 (preserving paragraph breaks)
    result = _MULTIPLE_NEWLINES.sub("\n\n", result)

    # 7. Remove standalone page-number lines (but NOT citation numbers)
    # Only remove lines that are JUST a number, not numbers inside text
    lines = result.split("\n")
    cleaned_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        # Keep empty lines (paragraph separators)
        if not stripped:
            cleaned_lines.append("")
            continue
        # Remove lines that are just a page number
        if _PAGE_NUMBER_LINE.match(stripped) and len(stripped) <= 6:
            continue
        cleaned_lines.append(line)
    result = "\n".join(cleaned_lines)

    # 8. Final trim
    result = result.strip()

    return result


def remove_repeated_headers_footers(
    page_texts: list[str],
    threshold: int = _REPEATED_LINE_THRESHOLD,
) -> list[str]:
    """Remove lines that appear on many pages (likely headers/footers).

    Only removes very short lines (< 100 chars) that repeat across
    at least ``threshold`` pages to avoid removing real content.

    Args:
        page_texts: List of per-page text strings.
        threshold: Minimum repetition count to flag a line.

    Returns:
        New list of page texts with repeated headers/footers removed.
    """
    if len(page_texts) < threshold:
        return page_texts

    # Count first and last 3 lines of each page
    line_counts: dict[str, int] = {}
    for text in page_texts:
        lines = text.strip().split("\n")
        edge_lines: set[str] = set()
        for line in lines[:3] + lines[-3:]:
            stripped = line.strip()
            if stripped and len(stripped) < 100:
                edge_lines.add(stripped)
        for line in edge_lines:
            line_counts[line] = line_counts.get(line, 0) + 1

    # Identify repeated lines
    repeated = {
        line for line, count in line_counts.items()
        if count >= threshold
    }

    if not repeated:
        return page_texts

    # Remove repeated lines from each page
    cleaned: list[str] = []
    for text in page_texts:
        lines = text.split("\n")
        filtered = [
            line for line in lines
            if line.strip() not in repeated
        ]
        cleaned.append("\n".join(filtered).strip())

    return cleaned
