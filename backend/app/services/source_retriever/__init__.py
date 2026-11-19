"""Research source retrieval service."""

from app.services.source_retriever.source_retriever import (
    get_source,
    list_document_sources,
    list_claim_sources,
    lookup_crossref_by_doi,
    normalize_doi,
    retrieve_metadata,
    retrieve_sources,
)

__all__ = [
    "get_source",
    "list_document_sources",
    "list_claim_sources",
    "lookup_crossref_by_doi",
    "normalize_doi",
    "retrieve_metadata",
    "retrieve_sources",
]
