"""Evidence extraction, chunking, embedding, and claim retrieval."""

from __future__ import annotations

import hashlib
import logging
import re
from html.parser import HTMLParser
from typing import Iterable
from uuid import UUID
import xml.etree.ElementTree as ET

import pymupdf
import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import verify_resource_ownership
from app.core.config import get_settings
from app.core.embedding import EMBEDDING_DIMENSION, EMBEDDING_MODEL
from app.core.vector_math import cosine_similarity
from app.models.document import Citation, Claim, Document, DocumentVersion
from app.models.enums import DocumentStatus, EvidenceContentType
from app.models.enums import SourceVersionType
from app.models.research import (
    Embedding,
    EvidencePassage,
    ResearchSource,
    SourceVersion,
)
from app.models.user import User

logger = logging.getLogger(__name__)
MAX_CHUNK_CHARS = 1200


class _TextHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.section = None
        self.paragraphs: list[tuple[str | None, str]] = []
        self.current: list[str] = []
        self.heading_level = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._flush()
            self.heading_level = int(tag[1])
        elif tag in {"p", "div", "section", "article"}:
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            heading = " ".join(self.current).strip()
            if heading:
                self.section = heading
            self.current = []
            self.heading_level = 0
        elif tag in {"p", "div", "section", "article"}:
            self._flush()

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.current.append(data.strip())

    def _flush(self) -> None:
        text = " ".join(self.current).strip()
        if text:
            self.paragraphs.append((self.section, text))
        self.current = []

    def result(self) -> list[tuple[str | None, str]]:
        self._flush()
        return [(section, text) for section, text in self.paragraphs if text]


def chunk_text(
    text: str,
    *,
    section_name: str | None = None,
    max_chars: int = MAX_CHUNK_CHARS,
) -> list[dict]:
    if not text or not text.strip():
        return []
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]
    chunks: list[dict] = []
    paragraph_number = 0
    for paragraph in paragraphs:
        paragraph_number += 1
        if len(paragraph) <= max_chars:
            chunks.append({
                "text": paragraph,
                "section_name": section_name,
                "paragraph_number": paragraph_number,
            })
            continue
        sentences = re.split(r"(?<=[.!?])\s+", paragraph)
        current = ""
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            if current and len(current) + len(sentence) + 1 > max_chars:
                chunks.append({
                    "text": current,
                    "section_name": section_name,
                    "paragraph_number": paragraph_number,
                })
                current = sentence
            elif len(sentence) > max_chars:
                for start in range(0, len(sentence), max_chars):
                    piece = sentence[start:start + max_chars].strip()
                    if piece:
                        chunks.append({
                            "text": piece,
                            "section_name": section_name,
                            "paragraph_number": paragraph_number,
                        })
                current = ""
            else:
                current = f"{current} {sentence}".strip()
        if current:
            chunks.append({
                "text": current,
                "section_name": section_name,
                "paragraph_number": paragraph_number,
            })
    return deduplicate_chunks(chunks)


def deduplicate_chunks(chunks: Iterable[dict]) -> list[dict]:
    seen: set[str] = set()
    result: list[dict] = []
    for chunk in chunks:
        text = " ".join(str(chunk["text"]).split())
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if digest in seen:
            continue
        seen.add(digest)
        result.append({**chunk, "text": text, "passage_hash": digest})
    return result


def parse_html(html: str) -> list[tuple[str | None, str]]:
    parser = _TextHTMLParser()
    parser.feed(html)
    return parser.result()


def parse_xml(xml_text: str) -> list[tuple[str | None, str]]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        logger.warning("Malformed evidence XML: %s", type(exc).__name__)
        return []
    namespace_free = re.compile(r"\{[^}]+\}")
    paragraphs: list[tuple[str | None, str]] = []
    section = None
    for element in root.iter():
        local_name = namespace_free.sub("", element.tag).lower()
        if local_name in {"title", "head", "section-title"}:
            text = "".join(element.itertext()).strip()
            if text:
                section = text
        elif local_name in {"p", "abstract", "sec"}:
            text = " ".join("".join(element.itertext()).split())
            if text:
                paragraphs.append((section, text))
    return deduplicate_paragraph_tuples(paragraphs)


def deduplicate_paragraph_tuples(
    paragraphs: Iterable[tuple[str | None, str]],
) -> list[tuple[str | None, str]]:
    seen: set[str] = set()
    result: list[tuple[str | None, str]] = []
    for section, text in paragraphs:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if digest not in seen:
            seen.add(digest)
            result.append((section, text))
    return result


def extract_pdf_text(data: bytes) -> list[tuple[int, str]]:
    try:
        document = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:
        logger.warning("Invalid evidence PDF: %s", type(exc).__name__)
        return []
    pages: list[tuple[int, str]] = []
    try:
        for page_number in range(document.page_count):
            text = document.load_page(page_number).get_text("text")
            if text.strip():
                pages.append((page_number + 1, text))
    finally:
        document.close()
    return pages


def extract_full_text(url: str) -> tuple[list[tuple[str | None, int | None, str]], str | None]:
    if not re.match(r"^https?://", url.strip(), re.I):
        return [], None
    settings = get_settings()
    try:
        response = httpx.get(
            url,
            timeout=settings.source_retrieval_timeout_seconds,
            headers={"Accept": "application/pdf,text/html,application/xml,text/xml,*/*"},
            follow_redirects=True,
        )
        response.raise_for_status()
    except Exception as exc:
        logger.warning("Evidence source inaccessible: %s", type(exc).__name__)
        return [], None

    content_type = response.headers.get("content-type", "").lower()
    if "pdf" in content_type or url.lower().endswith(".pdf"):
        pages = extract_pdf_text(response.content)
        return [
            (None, page_number, text)
            for page_number, text in pages
        ], "pymupdf_pdf"
    text = response.text
    if "xml" in content_type or url.lower().endswith(".xml"):
        return [
            (section, None, paragraph)
            for section, paragraph in parse_xml(text)
        ], "xml_etree"
    return [
        (section, None, paragraph)
        for section, paragraph in parse_html(text)
    ], "html_stdlib"


def generate_embeddings(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    try:
        from sentence_transformers import SentenceTransformer
    except Exception as exc:
        raise RuntimeError("Sentence Transformers model is unavailable") from exc
    try:
        model = SentenceTransformer(EMBEDDING_MODEL)
        vectors = model.encode(texts, batch_size=32, show_progress_bar=False)
    except Exception as exc:
        raise RuntimeError("Embedding model could not be loaded") from exc
    result = []
    for vector in vectors:
        values = [float(value) for value in vector]
        if len(values) != EMBEDDING_DIMENSION:
            raise RuntimeError(
                f"Embedding dimension mismatch: expected {EMBEDDING_DIMENSION}, got {len(values)}"
            )
        result.append(values)
    return result


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


def _source_ids_for_claim(claim_id: UUID, db: Session) -> list[UUID]:
    from app.models.document import ClaimCitation

    source_ids: list[UUID] = []
    links = list(db.execute(
        select(ClaimCitation).where(ClaimCitation.claim_id == claim_id)
    ).scalars().all())
    for link in links:
        citation = db.get(Citation, link.citation_id)
        if citation and citation.research_source_id:
            source_ids.append(citation.research_source_id)
    return list(dict.fromkeys(source_ids))


def _source_ids_for_document(version_id: UUID, db: Session) -> list[UUID]:
    citations = list(db.execute(
        select(Citation).where(
            Citation.document_version_id == version_id,
            Citation.research_source_id.is_not(None),
        )
    ).scalars().all())
    return list(dict.fromkeys(
        citation.research_source_id
        for citation in citations
        if citation.research_source_id is not None
    ))


def _ensure_source_version(source: ResearchSource, db: Session) -> SourceVersion:
    version = db.execute(
        select(SourceVersion)
        .where(SourceVersion.source_id == source.id)
        .order_by(SourceVersion.created_at.asc())
        .limit(1)
    ).scalar_one_or_none()
    if version is not None:
        return version
    version = SourceVersion(
        source_id=source.id,
        version_type=SourceVersionType.PUBLISHED,
        version_url=source.source_url,
        content_sha256=hashlib.sha256(
            (source.doi or source.title).encode("utf-8")
        ).hexdigest(),
        full_text_available=False,
        metadata_json={
            "passage_source": "phase8_metadata",
        },
    )
    db.add(version)
    db.flush()
    return version


def _add_abstract_passages(
    source: ResearchSource,
    source_version: SourceVersion,
    db: Session,
) -> int:
    if not source.abstract or not source.abstract.strip():
        return 0
    chunks = chunk_text(source.abstract, section_name="Abstract")
    added = 0
    for index, chunk in enumerate(chunks, start=1):
        existing = db.execute(
            select(EvidencePassage).where(
                EvidencePassage.source_version_id == source_version.id,
                EvidencePassage.passage_hash == chunk["passage_hash"],
            )
        ).scalar_one_or_none()
        if existing is not None:
            continue
        passage = EvidencePassage(
            source_id=source.id,
            source_version_id=source_version.id,
            passage_index=index,
            passage_text=chunk["text"],
            section_name=chunk["section_name"],
            page_number=None,
            paragraph_number=chunk["paragraph_number"],
            location=f"{source.title} | Abstract",
            content_type=EvidenceContentType.ABSTRACT,
            extraction_method="source_metadata_abstract",
            source_url=source.source_url,
            doi=source.doi,
            passage_hash=chunk["passage_hash"],
        )
        db.add(passage)
        added += 1
    db.flush()
    return added


def _add_full_text_passages(
    source: ResearchSource,
    source_version: SourceVersion,
    db: Session,
) -> int:
    url = source.source_url
    if not url:
        for version in source.versions:
            if version.version_url:
                url = version.version_url
                break
    if not url:
        return 0
    parsed, method = extract_full_text(url)
    if not parsed or not method:
        return 0
    existing_count = db.execute(
        select(EvidencePassage)
        .where(EvidencePassage.source_version_id == source_version.id)
    ).all()
    index = len(existing_count)
    added = 0
    for section, page_number, text in parsed:
        for chunk in chunk_text(text, section_name=section):
            existing = db.execute(
                select(EvidencePassage).where(
                    EvidencePassage.source_version_id == source_version.id,
                    EvidencePassage.passage_hash == chunk["passage_hash"],
                )
            ).scalar_one_or_none()
            if existing is not None:
                continue
            index += 1
            passage = EvidencePassage(
                source_id=source.id,
                source_version_id=source_version.id,
                passage_index=index,
                passage_text=chunk["text"],
                section_name=chunk["section_name"],
                page_number=page_number,
                paragraph_number=chunk["paragraph_number"],
                location=(
                    f"{source.title}"
                    f"{' | p.' + str(page_number) if page_number else ''}"
                ),
                content_type=EvidenceContentType.FULL_TEXT,
                extraction_method=method,
                source_url=url,
                doi=source.doi,
                passage_hash=chunk["passage_hash"],
            )
            db.add(passage)
            added += 1
    db.flush()
    return added


def _embed_new_passages(passages: list[EvidencePassage], db: Session) -> int:
    missing = []
    for passage in passages:
        if passage.embedding is None:
            missing.append(passage)
    if not missing:
        return 0
    vectors = generate_embeddings([passage.passage_text for passage in missing])
    for passage, vector in zip(missing, vectors):
        db.add(Embedding(
            evidence_passage_id=passage.id,
            vector=vector,
            model_name=EMBEDDING_MODEL,
        ))
    db.flush()
    return len(missing)


def extract_evidence_for_source_ids(
    source_ids: list[UUID],
    db: Session,
    *,
    include_full_text: bool = True,
) -> tuple[list[EvidencePassage], int, int]:
    passages: list[EvidencePassage] = []
    abstract_count = 0
    full_text_count = 0
    for source_id in source_ids:
        source = db.get(ResearchSource, source_id)
        if source is None:
            continue
        source_version = _ensure_source_version(source, db)
        abstract_count += _add_abstract_passages(source, source_version, db)
        if include_full_text:
            full_text_count += _add_full_text_passages(source, source_version, db)
        passages.extend(db.execute(
            select(EvidencePassage)
            .where(EvidencePassage.source_id == source.id)
            .order_by(EvidencePassage.passage_index)
        ).scalars().all())
    _embed_new_passages(passages, db)
    return passages, abstract_count, full_text_count


def retrieve_evidence(
    claim_id: UUID,
    source_ids: list[UUID],
    db: Session,
    *,
    page: int = 1,
    per_page: int = 20,
) -> dict:
    passages, abstract_count, full_text_count = extract_evidence_for_source_ids(
        source_ids,
        db,
    )
    claim = db.get(Claim, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")

    ranked: list[tuple[EvidencePassage, float]] = []
    try:
        claim_embedding = db.execute(
            select(Embedding).where(Embedding.claim_id == claim.id)
        ).scalar_one_or_none()
        if claim_embedding is None:
            vector = generate_embeddings([claim.normalized_text or claim.original_text])[0]
            claim_embedding = Embedding(
                claim_id=claim.id,
                vector=vector,
                model_name=EMBEDDING_MODEL,
            )
            db.add(claim_embedding)
            db.flush()
        claim_vector = list(claim_embedding.vector)
    except RuntimeError:
        claim_vector = None

    for passage in passages:
        if passage.embedding is not None:
            passage_vector = list(passage.embedding.vector)
        else:
            continue
        score = (
            cosine_similarity(claim_vector, passage_vector)
            if claim_vector is not None
            else 0.0
        )
        ranked.append((passage, score))
    ranked.sort(key=lambda item: item[1], reverse=True)
    offset = (page - 1) * per_page
    page_items = ranked[offset:offset + per_page]

    evidence = []
    for passage, score in page_items:
        source = db.get(ResearchSource, passage.source_id)
        evidence.append({
            "evidence_id": passage.id,
            "claim_id": claim.id,
            "source_id": passage.source_id,
            "publication_title": source.title if source else "Unknown source",
            "evidence_text": passage.passage_text,
            "content_type": passage.content_type,
            "section_name": passage.section_name,
            "page_number": passage.page_number,
            "paragraph_number": passage.paragraph_number,
            "source_url": passage.source_url,
            "doi": passage.doi,
            "extraction_method": passage.extraction_method,
            "similarity_score": score,
            "created_at": passage.created_at,
        })
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to persist evidence extraction")
        raise HTTPException(status_code=500, detail="Failed to persist evidence") from exc
    return {
        "claim_id": claim.id,
        "evidence": evidence,
        "total_evidence": len(ranked),
        "extraction_status": "completed",
    }


def extract_claim_evidence(
    claim_id: UUID,
    current_user: User,
    db: Session,
) -> dict:
    claim = db.get(Claim, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    doc = db.get(Document, claim.document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    verify_resource_ownership(doc.user_id, current_user)
    source_ids = _source_ids_for_claim(claim_id, db)
    return retrieve_evidence(claim_id, source_ids, db)


def list_claim_evidence(
    claim_id: UUID,
    current_user: User,
    db: Session,
    page: int = 1,
    per_page: int = 20,
) -> dict:
    claim = db.get(Claim, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    doc = db.get(Document, claim.document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    verify_resource_ownership(doc.user_id, current_user)
    return retrieve_evidence(
        claim_id,
        _source_ids_for_claim(claim_id, db),
        db,
        page=page,
        per_page=per_page,
    )


def list_source_evidence(
    source_id: UUID,
    current_user: User,
    db: Session,
    page: int = 1,
    per_page: int = 20,
) -> dict:
    source = db.get(ResearchSource, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Research source not found")
    citation = db.execute(
        select(Citation).where(Citation.research_source_id == source_id).limit(1)
    ).scalar_one_or_none()
    if citation is None:
        raise HTTPException(status_code=404, detail="Research source not found")
    doc = db.get(Document, citation.document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    verify_resource_ownership(doc.user_id, current_user)
    source_version = _ensure_source_version(source, db)
    passages = list(db.execute(
        select(EvidencePassage)
        .where(EvidencePassage.source_id == source_id)
        .order_by(EvidencePassage.passage_index)
    ).scalars().all())
    offset = (page - 1) * per_page
    evidence = []
    for passage in passages[offset:offset + per_page]:
        evidence.append({
            "evidence_id": passage.id,
            "claim_id": passage.claim_id,
            "source_id": passage.source_id,
            "publication_title": source.title,
            "evidence_text": passage.passage_text,
            "content_type": passage.content_type,
            "section_name": passage.section_name,
            "page_number": passage.page_number,
            "paragraph_number": passage.paragraph_number,
            "source_url": passage.source_url,
            "doi": passage.doi,
            "extraction_method": passage.extraction_method,
            "similarity_score": passage.relevance_score,
            "created_at": passage.created_at,
        })
    return {
        "source_id": source_id,
        "evidence": evidence,
        "total_evidence": len(passages),
        "extraction_status": "completed",
        "pagination": {
            "total": len(passages),
            "page": page,
            "per_page": per_page,
            "total_pages": (len(passages) + per_page - 1) // per_page,
        },
    }


def extract_document_evidence(
    document_id: UUID,
    current_user: User,
    db: Session,
) -> dict:
    doc = _owned_document(document_id, current_user, db)
    if doc.processing_status != DocumentStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="Document parsing has not completed")
    version = _latest_version(doc, db)
    source_ids = _source_ids_for_document(version.id, db)
    passages, abstract_count, full_text_count = extract_evidence_for_source_ids(
        source_ids,
        db,
    )
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to persist evidence") from exc
    evidence = []
    for passage in passages:
        source = db.get(ResearchSource, passage.source_id)
        evidence.append({
            "evidence_id": passage.id,
            "claim_id": passage.claim_id,
            "source_id": passage.source_id,
            "publication_title": source.title if source else "Unknown source",
            "evidence_text": passage.passage_text,
            "content_type": passage.content_type,
            "section_name": passage.section_name,
            "page_number": passage.page_number,
            "paragraph_number": passage.paragraph_number,
            "source_url": passage.source_url,
            "doi": passage.doi,
            "extraction_method": passage.extraction_method,
            "similarity_score": passage.relevance_score,
            "created_at": passage.created_at,
        })
    return {
        "document_id": doc.id,
        "version_id": version.id,
        "evidence": evidence,
        "total_evidence": len(evidence),
        "extraction_status": "completed",
        "abstract_passages_added": abstract_count,
        "full_text_passages_added": full_text_count,
    }


def list_document_evidence(
    document_id: UUID,
    current_user: User,
    db: Session,
    page: int = 1,
    per_page: int = 20,
) -> dict:
    doc = _owned_document(document_id, current_user, db)
    version = _latest_version(doc, db)
    source_ids = _source_ids_for_document(version.id, db)
    passages: list[EvidencePassage] = []
    for source_id in source_ids:
        passages.extend(db.execute(
            select(EvidencePassage)
            .where(EvidencePassage.source_id == source_id)
            .order_by(EvidencePassage.passage_index)
        ).scalars().all())
    offset = (page - 1) * per_page
    evidence = []
    for passage in passages[offset:offset + per_page]:
        source = db.get(ResearchSource, passage.source_id)
        evidence.append({
            "evidence_id": passage.id,
            "claim_id": passage.claim_id,
            "source_id": passage.source_id,
            "publication_title": source.title if source else "Unknown source",
            "evidence_text": passage.passage_text,
            "content_type": passage.content_type,
            "section_name": passage.section_name,
            "page_number": passage.page_number,
            "paragraph_number": passage.paragraph_number,
            "source_url": passage.source_url,
            "doi": passage.doi,
            "extraction_method": passage.extraction_method,
            "similarity_score": passage.relevance_score,
            "created_at": passage.created_at,
        })
    return {
        "document_id": doc.id,
        "version_id": version.id,
        "evidence": evidence,
        "total_evidence": len(passages),
        "extraction_status": "completed",
        "pagination": {
            "total": len(passages),
            "page": page,
            "per_page": per_page,
            "total_pages": (len(passages) + per_page - 1) // per_page,
        },
    }
