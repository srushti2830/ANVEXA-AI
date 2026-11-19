"""Verification verdict classification and Phase 10 service."""

from app.services.verdict_classifier.verification_service import (
    confidence_label,
    get_claim_verification,
    get_document_verification,
    get_verification_history,
    verify_claim,
    verify_document,
)

__all__ = [
    "confidence_label",
    "get_claim_verification",
    "get_document_verification",
    "get_verification_history",
    "verify_claim",
    "verify_document",
]
