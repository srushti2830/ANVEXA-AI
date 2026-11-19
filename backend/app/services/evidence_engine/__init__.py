"""Evidence extraction and ranking service."""

from app.services.evidence_engine.evidence_engine import (
    chunk_text,
    cosine_similarity,
    extract_full_text,
    extract_pdf_text,
    generate_embeddings,
    parse_html,
    parse_xml,
)

__all__ = [
    "chunk_text",
    "cosine_similarity",
    "extract_full_text",
    "extract_pdf_text",
    "generate_embeddings",
    "parse_html",
    "parse_xml",
]
