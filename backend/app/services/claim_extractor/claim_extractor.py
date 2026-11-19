"""Claim extraction service for Phase 5 parsed document content."""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

import httpx
from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette import status

from app.api.dependencies import verify_resource_ownership
from app.core.config import get_settings
from app.models.document import Claim, Document, DocumentPage, DocumentVersion
from app.models.enums import ClaimType, DocumentStatus, ExtractionStatus
from app.models.user import User

logger = logging.getLogger(__name__)

CITATION_PATTERNS = [
    re.compile(r"\[[0-9][0-9,\s;-]*\]"),
    re.compile(r"\([A-Z][A-Za-z.\-\s]+(?:et al\.?|and [A-Z][A-Za-z.-]+)?,\s*\d{4}[a-z]?\)", re.I),
    re.compile(r"\b[A-Z][A-Za-z.-]+(?:\s+(?:and|&)\s+[A-Z][A-Za-z.-]+)?\s*\(\d{4}[a-z]?\)", re.I),
    re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I),
]
BIBLIOGRAPHY_MARKERS = re.compile(
    r"^(references|bibliography|works cited|acknowledg(e)?ments?|table of contents)\s*$",
    re.I,
)
OPINION_MARKERS = re.compile(
    r"\b(i (?:think|believe|feel)|in my opinion|perhaps|maybe|seems desirable|beautiful|terrible)\b",
    re.I,
)
INCOMPLETE_MARKERS = re.compile(r"[.!?][\"\')\]]*$")
ABBREVIATIONS = re.compile(
    r"\b(?:Mr|Mrs|Ms|Dr|Prof|Fig|Figs|e\.g|i\.e|vs|etc|No|Vol|Eq|al)\.$",
    re.I,
)


class AIClaim(BaseModel):
    claim_text: str = Field(min_length=3)
    claim_type: str
    is_verifiable: bool = True
    extraction_reason: str = Field(min_length=3)
    confidence: float = Field(default=0.75, ge=0.0, le=1.0)


class AIClaimBatch(BaseModel):
    claims: list[AIClaim] = Field(default_factory=list)


@dataclass
class LocatedSentence:
    text: str
    page_number: int
    paragraph_index: int
    section_heading: str | None
    citation_markers: list[str]


def split_sentences(text: str) -> list[str]:
    """Rule-based sentence boundary splitter with abbreviations and DOI/citation protection."""
    if not text or not text.strip():
        return []
    protected = text
    # Protect decimal points and DOI periods during boundary detection.
    protected = re.sub(r"(?<=\d)\.(?=\d)", "<DECIMAL_DOT>", protected)
    protected = re.sub(
        r"(10\.\d{4,9}/[-._;()/:A-Z0-9]+)",
        lambda m: m.group(1).replace(".", "<DOI_DOT>"),
        protected,
        flags=re.I,
    )
    protected = re.sub(
        r"\b(Dr|Mr|Mrs|Ms|Prof|Fig|Figs|e\.g|i\.e|vs|etc|Vol|Eq)\.",
        lambda m: m.group(0).replace(".", "<ABBR_DOT>"),
        protected,
        flags=re.I,
    )
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\[\(])", protected)
    result: list[str] = []
    for part in parts:
        part = (
            part.replace("<DECIMAL_DOT>", ".")
            .replace("<DOI_DOT>", ".")
            .replace("<ABBR_DOT>", ".")
            .strip()
        )
        if ABBREVIATIONS.search(part) and len(result) == 0:
            continue
        if part:
            result.append(part)
    return result


def detect_citation_markers(text: str) -> list[str]:
    found: list[str] = []
    for pattern in CITATION_PATTERNS:
        for match in pattern.findall(text):
            marker = match.strip()
            if marker and marker not in found:
                found.append(marker)
    return found


def classify_claim(sentence: str) -> ClaimType:
    lower = sentence.lower()
    if re.search(r"\b(percent|percentage|p\s*[=<>]|confidence interval|odds ratio|p-value)\b", lower):
        return ClaimType.STATISTICAL
    if re.search(r"\b(higher|lower|greater|less|more|than|versus|compared with|outperforms)\b", lower):
        return ClaimType.COMPARATIVE
    if re.search(r"\b(causes?|caused|because|leads? to|increases?|decreases?|due to|results? in)\b", lower):
        return ClaimType.CAUSAL
    if re.search(r"\b(participants?|sample|method|protocol|procedure|randomized|survey|measurement)\b", lower):
        return ClaimType.METHODOLOGICAL
    if re.search(r"\b(patient|clinical|therapy|diagnosis|disease|treatment|mortality)\b", lower):
        return ClaimType.MEDICAL
    if re.search(r"\b(system|algorithm|model|software|hardware|cpu|sensor|api|network|protocol)\b", lower):
        return ClaimType.TECHNICAL
    if re.search(r"\b(established|founded|war|century|historical|in \d{3,4})\b", lower):
        return ClaimType.HISTORICAL
    if re.search(r"\b(shows?|found|demonstrated|discovered|observed|indicates?|reported|is|are|was|were)\b", lower):
        return ClaimType.SCIENTIFIC
    return ClaimType.GENERAL_FACTUAL


def is_claim_candidate(sentence: str) -> bool:
    text = sentence.strip()
    if len(text) < 12 or len(text.split()) < 4:
        return False
    if BIBLIOGRAPHY_MARKERS.match(text):
        return False
    if OPINION_MARKERS.search(text):
        return False
    if re.match(r"^(\d+[\s.)-]+)?[A-Za-z][A-Za-z0-9 &,-]{0,70}$", text) and len(text.split()) <= 8:
        return False
    if re.search(r"https?://|doi:\s*10\.", text, re.I) and len(text.split()) < 12:
        return False
    if not re.search(r"[A-Za-z]", text):
        return False
    if not INCOMPLETE_MARKERS.search(text) and not re.search(r"\b(?:is|are|was|were|has|have|found|reported)\b", text, re.I):
        return False
    return True


def locate_sentences(parsed_content: dict) -> list[LocatedSentence]:
    sentences: list[LocatedSentence] = []
    headings = re.compile(r"^(?:\d+(?:\.\d+)*\s+)?([A-Z][A-Za-z0-9 &/-]{2,80})$")
    current_heading: str | None = None
    for paragraph_index, page in enumerate(parsed_content.get("pages", [])):
        page_number = int(page.get("page_number") or 1)
        page_text = str(page.get("text") or "")
        metadata = page.get("metadata") or {}
        for block_index, paragraph in enumerate(re.split(r"\n{2,}|\r\n\r\n", page_text)):
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            lines = paragraph.splitlines()
            if lines:
                first = lines[0].strip()
                match = headings.match(first)
                if match and len(first.split()) <= 10:
                    current_heading = match.group(1).strip()
            paragraph_markers = detect_citation_markers(paragraph)
            for sentence in split_sentences(paragraph):
                sentence_markers = detect_citation_markers(sentence)
                combined = sentence_markers or paragraph_markers
                sentences.append(
                    LocatedSentence(
                        text=sentence,
                        page_number=page_number,
                        paragraph_index=block_index,
                        section_heading=current_heading,
                        citation_markers=combined,
                    )
                )
    return sentences


def rule_based_extract(located: list[LocatedSentence]) -> list[dict]:
    extracted: list[dict] = []
    seen: set[tuple[int, int, str]] = set()
    for item in located:
        if not is_claim_candidate(item.text):
            continue
        key = (item.page_number, item.paragraph_index, item.text.strip())
        if key in seen:
            continue
        seen.add(key)
        claim_type = classify_claim(item.text)
        extracted.append({
            "claim_text": item.text,
            "claim_type": claim_type.value,
            "is_verifiable": True,
            "extraction_reason": "Independently verifiable factual assertion detected by rule-based language patterns.",
            "confidence": 0.72 if claim_type != ClaimType.OTHER else 0.58,
        })
    return extracted


def gemini_extract(located: list[LocatedSentence]) -> tuple[list[dict], str | None]:
    settings = get_settings()
    if not settings.gemini_api_key:
        return [], "Gemini API key is not configured"

    selected = [item.text for item in located[:80] if is_claim_candidate(item.text)]
    if not selected:
        return [], None
    prompt = (
        "Extract only meaningful independently verifiable factual claims from the supplied sentences. "
        "Exclude opinions, headings, acknowledgements, references, navigation text, and incomplete sentences. "
        "Preserve exact original wording. Split compound sentences only when each resulting statement is factual "
        "and independently meaningful. Do not add facts or citations. "
        "Classify each as one of: scientific, statistical, comparative, causal, methodological, medical, technical, "
        "historical, general_factual, other. "
        "Return JSON only in the form {\"claims\":[{\"claim_text\":\"...\",\"claim_type\":\"...\","
        "\"is_verifiable\":true,\"extraction_reason\":\"...\",\"confidence\":0.85}]}.\n\nSentences:\n"
        + "\n".join(f"- {sentence}" for sentence in selected)
    )
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.gemini_model}:generateContent"
    )
    headers = {"x-goog-api-key": settings.gemini_api_key.get_secret_value()}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"},
    }
    last_error: Exception | None = None
    for attempt in range(settings.gemini_max_retries + 1):
        try:
            response = httpx.post(
                url,
                headers=headers,
                json=payload,
                timeout=settings.gemini_timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            text = text.strip()
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
                text = re.sub(r"\s*```$", "", text)
            parsed = AIClaimBatch.model_validate_json(text)
            original_map = {item.strip().lower(): item for item in selected}
            validated: list[dict] = []
            for claim in parsed.claims:
                exact = claim.claim_text.strip()
                if exact.lower() not in {sentence.strip().lower() for sentence in selected}:
                    continue
                if claim.claim_type not in {member.value for member in ClaimType}:
                    claim.claim_type = "general_factual"
                validated.append(claim.model_dump())
            return validated, None
        except Exception as exc:
            last_error = exc
            if attempt < settings.gemini_max_retries:
                time.sleep(0.25 * (attempt + 1))
    logger.warning("Gemini claim extraction failed: %s", type(last_error).__name__)
    return [], "Gemini extraction unavailable"


def _owned_document(document_id: UUID, current_user: User, db: Session) -> Document:
    doc = db.execute(select(Document).where(Document.id == document_id)).scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    verify_resource_ownership(doc.user_id, current_user)
    return doc


def extract_claims(document_id: UUID, current_user: User, db: Session) -> dict:
    doc = _owned_document(document_id, current_user, db)
    if doc.processing_status != DocumentStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document parsing has not completed",
        )
    version = db.execute(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == doc.id)
        .order_by(DocumentVersion.version_number.desc())
        .limit(1)
    ).scalar_one_or_none()
    if version is None:
        raise HTTPException(status_code=404, detail="Document has not been parsed yet")

    existing = list(
        db.execute(
            select(Claim)
            .where(Claim.document_version_id == version.id)
            .order_by(Claim.created_at)
        ).scalars().all()
    )
    if existing:
        return _response(doc, version, existing, existing[0].extraction_method or "cached")

    pages = list(
        db.execute(
            select(DocumentPage)
            .where(DocumentPage.document_version_id == version.id)
            .order_by(DocumentPage.page_number.asc())
        ).scalars().all()
    )
    if not pages or not any(p.extracted_text.strip() for p in pages):
        return _response(doc, version, [], "rule_based", ExtractionStatus.COMPLETED)

    parsed_content = {
        "document_id": str(doc.id),
        "version_id": str(version.id),
        "pages": [
            {"page_number": p.page_number, "text": p.extracted_text, "metadata": p.metadata_json}
            for p in pages
        ],
    }
    located = locate_sentences(parsed_content)
    ai_claims, ai_error = gemini_extract(located)
    method = "gemini"
    if ai_error or not ai_claims:
        ai_claims = rule_based_extract(located)
        method = "rule_based"

    sentence_lookup = {
        item.text.strip().lower(): item
        for item in located
    }
    created: list[Claim] = []
    for result in ai_claims:
        claim_text = str(result["claim_text"]).strip()
        location = sentence_lookup.get(claim_text.lower())
        if location is None:
            for item in located:
                if claim_text.lower() in item.text.lower():
                    location = item
                    break
        if location is None:
            continue
        claim_type = ClaimType(result.get("claim_type", "other"))
        claim = Claim(
            document_id=doc.id,
            document_version_id=version.id,
            page_id=next((p.id for p in pages if p.page_number == location.page_number), None),
            page_number=location.page_number,
            paragraph_number=location.paragraph_index,
            original_text=location.text,
            normalized_text=claim_text,
            context_text=location.text,
            claim_type=claim_type,
            requires_external_verification=bool(result.get("is_verifiable", True)),
            section_heading=location.section_heading,
            extraction_confidence=float(result.get("confidence", 0.72)),
            citation_markers=location.citation_markers,
            extraction_reason=str(result.get("extraction_reason", "Factual assertion")),
            extraction_method=method,
            extraction_status=ExtractionStatus.COMPLETED,
        )
        db.add(claim)
        created.append(claim)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to persist extracted claims")
        raise HTTPException(status_code=500, detail="Failed to save claim extraction results") from exc
    for claim in created:
        db.refresh(claim)
    return _response(doc, version, created, method, ExtractionStatus.COMPLETED)


def list_claims(
    document_id: UUID,
    current_user: User,
    db: Session,
    page: int = 1,
    per_page: int = 20,
) -> dict:
    doc = _owned_document(document_id, current_user, db)
    version = db.execute(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == doc.id)
        .order_by(DocumentVersion.version_number.desc())
        .limit(1)
    ).scalar_one_or_none()
    if version is None:
        raise HTTPException(status_code=404, detail="Document has not been parsed yet")
    total = len(list(db.execute(select(Claim).where(
        Claim.document_version_id == version.id
    ).order_by(Claim.created_at)).scalars().all()))
    claims = list(
        db.execute(
            select(Claim)
            .where(Claim.document_version_id == version.id)
            .order_by(Claim.created_at)
            .offset((page - 1) * per_page)
            .limit(per_page)
        ).scalars().all()
    )
    return {
        "document_id": doc.id,
        "version_id": version.id,
        "claims": claims,
        "pagination": {
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": (total + per_page - 1) // per_page,
        },
    }


def get_claim(claim_id: UUID, current_user: User, db: Session) -> Claim:
    claim = db.execute(select(Claim).where(Claim.id == claim_id)).scalar_one_or_none()
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    doc = db.execute(select(Document).where(Document.id == claim.document_id)).scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    verify_resource_ownership(doc.user_id, current_user)
    return claim


def _response(
    doc: Document,
    version: DocumentVersion,
    claims: list[Claim],
    method: str,
    status_value: ExtractionStatus = ExtractionStatus.COMPLETED,
) -> dict:
    return {
        "document_id": doc.id,
        "version_id": version.id,
        "version_number": version.version_number,
        "extracted_count": len(claims),
        "extraction_method": method,
        "processing_status": status_value,
        "claims": claims,
    }
