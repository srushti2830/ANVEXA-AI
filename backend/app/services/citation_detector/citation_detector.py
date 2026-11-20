"""Citation detection and claim-to-citation mapping for parsed documents."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import verify_resource_ownership
from app.models.document import (
    Claim,
    ClaimCitation,
    Citation,
    Document,
    DocumentPage,
    DocumentVersion,
)
from app.models.enums import (
    CitationMappingStatus,
    CitationStyle,
    DocumentStatus,
)
from app.models.user import User


@dataclass(frozen=True)
class DetectedMarker:
    original: str
    normalized: str
    style: CitationStyle
    page_number: int
    paragraph_index: int
    character_offset: int


NUMBERED_MARKER = re.compile(r"\[(\d+(?:\s*[,-]\s*\d+)*)\]")
PAREN_AUTHOR_YEAR = re.compile(
    r"\(([^()]*\b(?:19|20)\d{2}[a-z]?[^()]*)\)"
)
NAMED_AUTHOR_YEAR = re.compile(
    r"\b[A-Z][A-Za-z.-]*(?:\s+(?:and|&)\s+[A-Z][A-Za-z.-]*)?"
    r"\s*\(\s*((?:19|20)\d{2}[a-z]?)\s*\)",
)
SUPERSCRIPT_NUMBER = re.compile(r"(?<!\[)\b\d{1,4}(?!\])(?=[,.;\s]|$)")
DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)
REFERENCE_HEADING = re.compile(
    r"^(?:references|bibliography|works cited|literature cited)\s*$",
    re.I,
)


def normalize_marker(marker: str) -> str:
    marker = marker.strip()
    if marker.startswith("[") and marker.endswith("]"):
        inside = marker[1:-1]
        numbers = re.findall(r"\d+", inside)
        return "numeric:" + ",".join(str(int(n)) for n in numbers)
    marker = re.sub(r"\s+", " ", marker)
    marker = re.sub(r"\bet al\.?\b", "et-al", marker, flags=re.I)
    marker = marker.lower()
    marker = marker.strip("() ")
    marker = re.sub(r"\s*&\s*", " and ", marker)
    return "author_year:" + re.sub(r"\s+", " ", marker).strip()


def detect_style(marker: str) -> CitationStyle:
    if marker.startswith("[") and marker.endswith("]"):
        return CitationStyle.NUMERIC
    if re.search(r"\(\s*(?:19|20)\d{2}[a-z]?\s*\)", marker):
        return CitationStyle.APA
    if re.search(r"\b(?:19|20)\d{2}[a-z]?\b", marker):
        return CitationStyle.AUTHOR_YEAR
    if DOI_RE.search(marker):
        return CitationStyle.UNKNOWN
    return CitationStyle.UNKNOWN


def detect_markers(text: str, page_number: int, paragraph_index: int) -> list[DetectedMarker]:
    markers: list[DetectedMarker] = []
    for match in NUMBERED_MARKER.finditer(text):
        original = match.group(0)
        markers.append(DetectedMarker(
            original,
            normalize_marker(original),
            detect_style(original),
            page_number,
            paragraph_index,
            match.start(),
        ))
    for match in PAREN_AUTHOR_YEAR.finditer(text):
        original = match.group(0)
        markers.append(DetectedMarker(
            original,
            normalize_marker(original),
            detect_style(original),
            page_number,
            paragraph_index,
            match.start(),
        ))
    for match in NAMED_AUTHOR_YEAR.finditer(text):
        original = match.group(0)
        markers.append(DetectedMarker(
            original,
            normalize_marker(original),
            detect_style(original),
            page_number,
            paragraph_index,
            match.start(),
        ))
    for match in DOI_RE.finditer(text):
        original = match.group(0)
        markers.append(DetectedMarker(
            original,
            "doi:" + original.lower(),
            CitationStyle.UNKNOWN,
            page_number,
            paragraph_index,
            match.start(),
        ))
    unique: dict[tuple[str, int], DetectedMarker] = {}
    for marker in markers:
        unique[(marker.normalized, marker.character_offset)] = marker
    return sorted(unique.values(), key=lambda item: item.character_offset)


def _split_reference_lines(text: str) -> list[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    entries: list[str] = []
    for line in lines:
        if re.match(r"^\s*(?:\[\d+\]|(?:\d+)[.)])\s+", line):
            entries.append(line)
        elif re.match(r"^\s*[A-Z][A-Za-z.\-]+(?:,\s*[A-Z][A-Za-z.\-]*)?.{0,3}(?:19|20)\d{2}[a-z]?", line):
            entries.append(line)
        else:
            if entries:
                entries[-1] = entries[-1] + " " + line
            else:
                entries.append(line)
    return entries


def extract_reference_entry(entry: str) -> dict:
    result: dict = {
        "citation_text": entry,
        "authors": [],
        "publication_year": None,
        "publication_title": None,
        "journal_or_conference": None,
        "volume": None,
        "issue": None,
        "page_range": None,
        "doi": None,
        "url": None,
        "reference_number": None,
    }
    year_match = re.search(r"\b((?:19|20)\d{2}[a-z]?)\b", entry)
    if year_match:
        try:
            result["publication_year"] = int(year_match.group(1)[:4])
        except ValueError:
            pass
    doi_match = DOI_RE.search(entry)
    if doi_match:
        result["doi"] = doi_match.group(0)
    url_match = re.search(r"https?://\S+", entry)
    if url_match:
        result["url"] = url_match.group(0).rstrip(".,)")
    number_match = re.match(r"^\s*\[?(\d+)\]?[.)]\s*", entry)
    if number_match:
        result["reference_number"] = number_match.group(1)
    numbered_marker = re.match(r"^\s*\[(\d+)\]", entry)
    if numbered_marker:
        result["reference_number"] = numbered_marker.group(1)
    author_match = re.match(r"^(.{1,180}?)(?:\.\s|\s\()", entry)
    if author_match:
        authors_text = author_match.group(1).strip()
        if authors_text:
            result["authors"] = [
                author.strip()
                for author in re.split(r"\s+(?:and|&)\s+|;\s*", authors_text)
                if author.strip()
            ]
    volume_issue = re.search(r"\b(\d+)\s*\(\s*(\d+)\s*\)", entry)
    if volume_issue:
        result["volume"] = volume_issue.group(1)
        result["issue"] = volume_issue.group(2)
    pages_match = re.search(r"(?:pp?\.\s*)?(\d{1,5}\s*[-–]\s*\d{1,5})", entry)
    if pages_match:
        result["page_range"] = pages_match.group(1).replace(" ", "")
    return result


def _owned_document(document_id: UUID, current_user: User, db: Session) -> Document:
    doc = db.execute(select(Document).where(Document.id == document_id)).scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    verify_resource_ownership(doc.user_id, current_user)
    return doc


def detect_citations(document_id: UUID, current_user: User, db: Session) -> dict:
    doc = _owned_document(document_id, current_user, db)
    if doc.processing_status != DocumentStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="Document parsing has not completed")

    version = db.execute(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == doc.id)
        .order_by(DocumentVersion.version_number.desc())
        .limit(1)
    ).scalar_one_or_none()
    if version is None:
        raise HTTPException(status_code=404, detail="Document has not been parsed yet")

    existing_links = list(db.execute(
        select(ClaimCitation).join(Citation).where(Citation.document_version_id == version.id)
    ).scalars().all())
    existing_citations = list(db.execute(
        select(Citation).where(Citation.document_version_id == version.id)
        .order_by(Citation.created_at)
    ).scalars().all())
    if existing_citations:
        return _citation_response(doc, version, existing_citations, len(existing_links))

    pages = list(db.execute(
        select(DocumentPage)
        .where(DocumentPage.document_version_id == version.id)
        .order_by(DocumentPage.page_number.asc())
    ).scalars().all())

    detected: list[DetectedMarker] = []
    reference_entries: list[Citation] = []
    in_references = False
    for page in pages:
        paragraph_parts = re.split(r"\n{2,}|\r\n\r\n", page.extracted_text)
        for paragraph_index, paragraph in enumerate(paragraph_parts):
            first_line = paragraph.strip().splitlines()[0].strip() if paragraph.strip() else ""
            if REFERENCE_HEADING.match(first_line):
                in_references = True
                continue
            if in_references:
                for entry_text in _split_reference_lines(paragraph):
                    fields = extract_reference_entry(entry_text)
                    style = (
                        CitationStyle.NUMERIC
                        if fields["reference_number"] is not None
                        else CitationStyle.APA
                    )
                    citation = Citation(
                        document_id=doc.id,
                        document_version_id=version.id,
                        citation_text=entry_text,
                        original_marker=entry_text,
                        normalized_marker=(
                            "numeric:" + fields["reference_number"]
                            if fields["reference_number"] is not None
                            else "author_year:" + entry_text.lower()[:500]
                        ),
                        citation_type=style,
                        reference_number=fields["reference_number"],
                        authors=fields["authors"],
                        publication_year=fields["publication_year"],
                        publication_title=fields["publication_title"],
                        journal_or_conference=fields["journal_or_conference"],
                        volume=fields["volume"],
                        issue=fields["issue"],
                        page_range=fields["page_range"],
                        doi=fields["doi"],
                        url=fields["url"],
                        page_number=page.page_number,
                        paragraph_number=paragraph_index,
                        is_bibliography_entry=True,
                        extraction_method="rule_based",
                    )
                    db.add(citation)
                    reference_entries.append(citation)
                continue
            for marker in detect_markers(paragraph, page.page_number, paragraph_index):
                detected.append(marker)

    db.flush()

    citation_by_marker: dict[str, list[Citation]] = {}
    for citation in reference_entries:
        citation_by_marker.setdefault(citation.normalized_marker or "", []).append(citation)

    for marker in detected:
        citation = next(
            (
                existing
                for existing in db.execute(
                    select(Citation).where(
                        Citation.document_version_id == version.id,
                        Citation.normalized_marker == marker.normalized,
                        Citation.citation_text == marker.original,
                    )
                ).scalars().all()
            ),
            None,
        )
        if citation is None:
            citation = Citation(
                document_id=doc.id,
                document_version_id=version.id,
                citation_text=marker.original,
                original_marker=marker.original,
                normalized_marker=marker.normalized,
                citation_type=marker.style,
                page_number=marker.page_number,
                paragraph_number=marker.paragraph_index,
                is_bibliography_entry=False,
                extraction_method="rule_based",
            )
            db.add(citation)
            db.flush()

    db.flush()

    claims = list(db.execute(
        select(Claim)
        .where(Claim.document_version_id == version.id)
        .order_by(Claim.created_at)
    ).scalars().all())

    mapping_count = 0
    for claim in claims:
        claim_markers = detect_markers(claim.original_text, claim.page_number or 1, claim.paragraph_number or 0)
        if not claim_markers:
            same_page_markers = [
                marker for marker in detected
                if marker.page_number == claim.page_number
            ]
            claim_markers = same_page_markers[:1]
        for marker in claim_markers:
            candidates = db.execute(
                select(Citation).where(
                    Citation.document_version_id == version.id,
                    Citation.normalized_marker == marker.normalized,
                )
            ).scalars().all()
            if candidates:
                mapping_status = CitationMappingStatus.MATCHED
                citation = candidates[0]
            elif marker.normalized.startswith("numeric:"):
                number = marker.normalized.split(":", 1)[1].split(",")
                reference_matches = [
                    citation for citation in reference_entries
                    if citation.reference_number in number
                ]
                if len(reference_matches) == 1:
                    mapping_status = CitationMappingStatus.MATCHED
                    citation = reference_matches[0]
                elif len(reference_matches) > 1:
                    mapping_status = CitationMappingStatus.MULTIPLE_MATCHES
                    citation = reference_matches[0]
                else:
                    mapping_status = CitationMappingStatus.MISSING_REFERENCE
                    citation = None
            else:
                matching_references = [
                    citation for citation in reference_entries
                    if citation.normalized_marker
                    and citation.normalized_marker != ""
                    and citation.normalized_marker in marker.normalized
                ]
                if len(matching_references) == 1:
                    mapping_status = CitationMappingStatus.MATCHED
                    citation = matching_references[0]
                elif len(matching_references) > 1:
                    mapping_status = CitationMappingStatus.MULTIPLE_MATCHES
                    citation = matching_references[0]
                else:
                    mapping_status = CitationMappingStatus.UNMATCHED
                    citation = None

            if citation is None:
                unmapped_marker = db.execute(
                    select(Citation).where(
                        Citation.document_version_id == version.id,
                        Citation.normalized_marker == marker.normalized,
                        Citation.citation_text == marker.original,
                    )
                ).scalar_one_or_none()
                if unmapped_marker is None:
                    unmapped_marker = Citation(
                        document_id=doc.id,
                        document_version_id=version.id,
                        citation_text=marker.original,
                        original_marker=marker.original,
                        normalized_marker=marker.normalized,
                        citation_type=marker.style,
                        page_number=marker.page_number,
                        paragraph_number=marker.paragraph_index,
                        is_bibliography_entry=False,
                        extraction_method="rule_based",
                    )
                    db.add(unmapped_marker)
                    db.flush()
                citation = unmapped_marker

            existing = db.execute(
                select(ClaimCitation).where(
                    ClaimCitation.claim_id == claim.id,
                    ClaimCitation.citation_id == citation.id,
                )
            ).scalar_one_or_none()
            if existing is None:
                db.add(ClaimCitation(
                    claim_id=claim.id,
                    citation_id=citation.id,
                    citation_text=marker.original,
                    normalized_marker=marker.normalized,
                    page_number=marker.page_number,
                    paragraph_number=marker.paragraph_index,
                    character_offset=marker.character_offset,
                    mapping_status=mapping_status,
                    mapping_method="exact_normalized_marker",
                ))
                mapping_count += 1

    db.commit()
    citations = list(db.execute(
        select(Citation)
        .where(Citation.document_version_id == version.id)
        .order_by(Citation.created_at)
    ).scalars().all())
    return _citation_response(doc, version, citations, mapping_count)


def _citation_response(
    doc: Document,
    version: DocumentVersion,
    citations: Iterable[Citation],
    mapping_count: int,
) -> dict:
    citation_list = list(citations)
    reference_count = sum(1 for citation in citation_list if citation.is_bibliography_entry)
    return {
        "document_id": doc.id,
        "version_id": version.id,
        "version_number": version.version_number,
        "detected_count": len(citation_list),
        "reference_count": reference_count,
        "mapping_count": mapping_count,
        "extraction_method": (
            citation_list[0].extraction_method
            if citation_list and citation_list[0].extraction_method
            else "rule_based"
        ),
        "citations": citation_list,
    }
