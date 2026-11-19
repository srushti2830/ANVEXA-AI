"""Document parsing service — PDF, DOCX text extraction with optional OCR."""

from app.services.document_parser.parser_service import (
    get_parsed_content,
    parse_document,
)

__all__ = [
    "parse_document",
    "get_parsed_content",
]
