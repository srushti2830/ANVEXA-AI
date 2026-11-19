"""Evidence extraction, chunking, embedding, and claim retrieval."""

from __future__ import annotations

import hashlib
import logging
import math
import re
from html.parser import HTMLParser
from typing import Iterable
from uuid import UUID
import xml.etree.ElementTree as ET

import fitz
import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import verify_resource_ownership
from app.core.config import get_settings
from app.core.embedding import EMBEDDING_DIMENSION, EMBEDDING_MODEL
from app.models.document import Citation, Claim, Document, DocumentVersion
from app.models.enums import DocumentStatus, EvidenceContentType
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
        document = fitz.open(stream=data, filetype="pdf")
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


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return max(-1.0, min(1.0, dot / (left_norm * right_norm)))


def _owned_document(document_id: UUID, current_user: User, db: Session) -> Document:
    doc = db.execute(select(Document).where(Document.id == document_id)).scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    verify_resource_ownership(doc.user_id, current_user)
    return doc
