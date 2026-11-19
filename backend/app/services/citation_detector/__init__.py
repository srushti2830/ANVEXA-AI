"""Citation detection and mapping service."""

from app.services.citation_detector.citation_detector import (
    detect_citations,
    detect_markers,
    detect_style,
    extract_reference_entry,
    normalize_marker,
)

__all__ = [
    "detect_citations",
    "detect_markers",
    "detect_style",
    "extract_reference_entry",
    "normalize_marker",
]
