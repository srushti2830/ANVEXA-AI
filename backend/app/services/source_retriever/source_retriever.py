"""Research source metadata retrieval for Phase 7 citations.

This phase retrieves source metadata only. It does not download full text,
create evidence passages, or evaluate whether a source supports a claim.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import verify_resource_ownership
from app.core.config import get_settings
from app.models.document import Citation, Document, DocumentVersion
from app.models.enums import (
    DocumentStatus,
    RetrievalStatus,
    SourceVersionType,
)
from app.models.research import ResearchSource, SourceVersion
from app.models.user import User

logger = logging.getLogger(__name__)
DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)


def normalize_doi(value: str | None) -> str | None:
    if not value:
        return None
    match = DOI_RE.search(value.strip())
    return match.group(0).lower().rstrip(".,;)") if match else None


def _request_json(url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = get_settings()
    last_error: Exception | None = None
    headers = {
        "Accept": "application/json",
        "User-Agent": "ANVEXA-AI/1.0 (research-source-retrieval)",
    }
    for attempt in range(settings.source_retrieval_max_retries + 1):
        try:
            response = httpx.get(
                url,
                params=params,
                headers=headers,
                timeout=settings.source_retrieval_timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, dict) else {}
        except Exception as exc:
            last_error = exc
            if attempt < settings.source_retrieval_max_retries:
                time.sleep(0.25 * (attempt + 1))
    logger.warning("Research metadata retrieval failed: %s", type(last_error).__name__)
    return {}


def lookup_crossref_by_doi(doi: str) -> dict[str, Any] | None:
    settings = get_settings()
    clean_doi = normalize_doi(doi)
    if not clean_doi:
        return None
    data = _request_json(f"{settings.crossref_api_url}/works/{clean_doi}")
    message = data.get("message")
    if not isinstance(message, dict):
        return None
    authors = []
    for author in message.get("author", []) or []:
        if isinstance(author, dict):
            name = " ".join(
                part for part in (
                    author.get("given"),
                    author.get("family"),
                ) if isinstance(part, str) and part
            ).strip()
            if name:
                authors.append(name)
    published = message.get("published-print") or message.get("published-online")
    year = None
    if isinstance(published, dict):
        date_parts = published.get("date-parts")
        if isinstance(date_parts, list) and date_parts and isinstance(date_parts[0], list):
            if date_parts[0]:
                year = date_parts[0][0]
    title_values = message.get("title")
    title = title_values[0] if isinstance(title_values, list) and title_values else "Unknown source"
    journal_values = message.get("container-title")
    journal = journal_values[0] if isinstance(journal_values, list) and journal_values else None
    url = message.get("URL") or f"https://doi.org/{clean_doi}"
    return {
        "doi": normalize_doi(message.get("DOI") or clean_doi),
        "title": title if isinstance(title, str) and title else "Unknown source",
        "authors": authors,
        "publication_year": int(year) if isinstance(year, int) else None,
        "journal": journal if isinstance(journal, str) else None,
        "source_url": url if isinstance(url, str) else f"https://doi.org/{clean_doi}",
        "abstract": message.get("abstract") if isinstance(message.get("abstract"), str) else None,
        "provider": "crossref",
        "provider_id": clean_doi,
        "raw": message,
    }


def lookup_crossref_by_query(citation: Citation) -> dict[str, Any] | None:
    settings = get_settings()
    query = citation.publication_title or citation.citation_text
    if not query or len(query.strip()) < 3:
        return None
    data = _request_json(
        f"{settings.crossref_api_url}/works",
        {
            "query.bibliographic": query,
            "rows": 5,
        },
    )
    items = data.get("message", {}).get("items", []) if isinstance(data.get("message"), dict) else []
    if not isinstance(items, list) or not items:
        return None

    best = None
    for item in items:
        if not isinstance(item, dict):
            continue
        candidate_title_values = item.get("title")
        candidate_title = (
            candidate_title_values[0]
            if isinstance(candidate_title_values, list) and candidate_title_values
            else ""
        )
        if citation.publication_title:
            if candidate_title.lower().strip() != citation.publication_title.lower().strip():
                continue
        best = item
        break
    if best is None:
        best = items[0]
    doi = normalize_doi(best.get("DOI"))
    title_values = best.get("title")
    title = title_values[0] if isinstance(title_values, list) and title_values else "Unknown source"
    return {
        "doi": doi,
        "title": title if isinstance(title, str) else "Unknown source",
        "authors": [
            " ".join(
                part for part in (author.get("given"), author.get("family"))
                if isinstance(part, str) and part
            ).strip()
            for author in (best.get("author") or [])
            if isinstance(author, dict)
        ],
        "publication_year": (
            best.get("published", {}).get("date-parts", [[None]])[0][0]
            if isinstance(best.get("published"), dict)
            else None
        ),
        "journal": (
            best.get("container-title", [None])[0]
            if isinstance(best.get("container-title"), list) and best.get("container-title")
            else None
        ),
        "source_url": best.get("URL") or (f"https://doi.org/{doi}" if doi else None),
        "abstract": best.get("abstract") if isinstance(best.get("abstract"), str) else None,
        "provider": "crossref",
        "provider_id": doi or str(best.get("id", "")),
        "raw": best,
    }


def lookup_openalex_by_doi(doi: str) -> dict[str, Any] | None:
    settings = get_settings()
    clean_doi = normalize_doi(doi)
    if not clean_doi:
        return None
    data = _request_json(
        f"{settings.openalex_api_url}/works/https://doi.org/{clean_doi}"
    )
    if not data or not isinstance(data.get("title"), str):
        return None
    authorships = data.get("authorships") or []
    authors = []
    if isinstance(authorships, list):
        for authorship in authorships:
            if not isinstance(authorship, dict):
                continue
            author = authorship.get("author")
            if isinstance(author, dict) and isinstance(author.get("display_name"), str):
                authors.append(author["display_name"])
    locations = data.get("locations") or []
    source_url = data.get("doi") or data.get("id")
    if isinstance(locations, list):
        for location in locations:
            if isinstance(location, dict) and location.get("is_best") and isinstance(location.get("landing_page_url"), str):
                source_url = location["landing_page_url"]
                break
    return {
        "doi": normalize_doi(data.get("doi")),
        "title": data["title"],
        "authors": authors,
        "publication_year": data.get("publication_year") if isinstance(data.get("publication_year"), int) else None,
        "journal": (
            data.get("primary_location", {}).get("source", {}).get("display_name")
            if isinstance(data.get("primary_location"), dict)
            and isinstance(data.get("primary_location", {}).get("source"), dict)
            else None
        ),
        "source_url": source_url if isinstance(source_url, str) else None,
        "abstract": None,
        "provider": "openalex",
        "provider_id": data.get("id") if isinstance(data.get("id"), str) else clean_doi,
        "raw": data,
    }


def retrieve_metadata(citation: Citation) -> dict[str, Any] | None:
    doi = normalize_doi(citation.doi)
    if doi:
        metadata = lookup_crossref_by_doi(doi)
        if metadata:
            return metadata
        metadata = lookup_openalex_by_doi(doi)
        if metadata:
            return metadata
    return lookup_crossref_by_query(citation)


def _owned_document(document_id: UUID, current_user: User, db: Session) -> Document:
    doc = db.execute(select(Document).where(Document.id == document_id)).scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    verify_resource_ownership(doc.user_id, current_user)
    return doc


def _latest_version(document: Document, db: Session) -> DocumentVersion:
    version = db.execute(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == document.id)
        .order_by(DocumentVersion.version_number.desc())
        .limit(1)
    ).scalar_one_or_none()
    if version is None:
        raise HTTPException(status_code=404, detail="Document has not been parsed yet")
    return version


def retrieve_sources(document_id: UUID, current_user: User, db: Session) -> dict:
    doc = _owned_document(document_id, current_user, db)
    if doc.processing_status != DocumentStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="Document parsing has not completed")
    version = _latest_version(doc, db)

    citations = list(db.execute(
        select(Citation)
        .where(
            Citation.document_version_id == version.id,
            Citation.is_bibliography_entry.is_(True),
        )
        .order_by(Citation.created_at)
    ).scalars().all())

    sources: list[ResearchSource] = []
    unavailable_count = 0
    duplicate_count = 0
    for citation in citations:
        metadata = retrieve_metadata(citation)
        if not metadata:
            unavailable_count += 1
            citation.research_source_id = None
            continue

        doi = normalize_doi(metadata.get("doi"))
        source = None
        if doi:
            source = db.execute(
                select(ResearchSource).where(ResearchSource.doi == doi)
            ).scalar_one_or_none()
        if source is None:
            source = db.execute(
                select(ResearchSource).where(
                    ResearchSource.title == metadata["title"],
                    ResearchSource.publication_year.is_not_distinct_from(metadata.get("publication_year")),
                )
            ).scalar_one_or_none()

        if source is None:
            source = ResearchSource(
                doi=doi,
                title=metadata["title"],
                authors=metadata.get("authors") or [],
                publication_year=metadata.get("publication_year"),
                journal=metadata.get("journal"),
                source_url=metadata.get("source_url"),
                abstract=metadata.get("abstract"),
                retrieval_status=RetrievalStatus.METADATA_ONLY,
                is_retracted=False,
                metadata_json={
                    "provider": metadata.get("provider"),
                    "provider_id": metadata.get("provider_id"),
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            db.add(source)
            db.flush()
        else:
            duplicate_count += 1

        citation.research_source_id = source.id
        raw = metadata.get("raw")
        snapshot_text = repr(raw) if raw is not None else metadata["title"]
        content_sha256 = hashlib.sha256(snapshot_text.encode("utf-8")).hexdigest()
        snapshot = db.execute(
            select(SourceVersion).where(
                SourceVersion.source_id == source.id,
                SourceVersion.content_sha256 == content_sha256,
            )
        ).scalar_one_or_none()
        if snapshot is None:
            snapshot = SourceVersion(
                source_id=source.id,
                version_type=SourceVersionType.PUBLISHED,
                version_url=source.source_url,
                content_sha256=content_sha256,
                published_at=None,
                full_text_available=False,
                metadata_json={
                    "provider": metadata.get("provider"),
                    "retrieval_method": "metadata_api",
                },
            )
            db.add(snapshot)
            db.flush()

        if source not in sources:
            sources.append(source)

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to persist research source retrieval")
        raise HTTPException(status_code=500, detail="Failed to persist source retrieval") from exc

    for source in sources:
        db.refresh(source)
    return {
        "document_id": doc.id,
        "version_id": version.id,
        "retrieved_count": len(sources),
        "unavailable_count": unavailable_count,
        "duplicate_count": duplicate_count,
        "extraction_method": "crossref_openalex_metadata",
        "sources": sources,
    }
