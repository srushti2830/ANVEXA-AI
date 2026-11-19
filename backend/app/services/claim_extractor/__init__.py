"""Claim extraction service."""

from app.services.claim_extractor.claim_extractor import (
    extract_claims,
    get_claim,
    list_claims,
    locate_sentences,
    rule_based_extract,
    split_sentences,
)

__all__ = [
    "extract_claims",
    "get_claim",
    "list_claims",
    "locate_sentences",
    "rule_based_extract",
    "split_sentences",
]
