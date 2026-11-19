"""Document parsing service — PDF and DOCX text extraction."""

from app.services.document_parser.parser_service import (
    get_document_full_text,
    get_document_page,
    get_document_pages,
    parse_document,
)

__all__ = [
    "parse_document",
    "get_document_pages",
    "get_document_page",
    "get_document_full_text",
]
