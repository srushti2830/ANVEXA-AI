# Phase 9 Completion Report

## Implementation status

Phase 9 evidence extraction, chunking, embedding, and semantic ranking has been implemented.

## Files created

- `backend/app/schemas/evidence.py`
- `backend/app/api/endpoints/evidence.py`
- `backend/app/services/evidence_engine/evidence_engine.py`
- `backend/tests/test_evidence_engine.py`
- `backend/migrations/versions/20261119_0006_phase9_evidence_embeddings.py`
- `backend/docs/phase9_evidence_embeddings.md`
- `PHASE9_COMPLETION_REPORT.md`

## Files modified

- `backend/app/models/enums.py`
- `backend/app/models/document.py`
- `backend/app/models/research.py`
- `backend/app/models/__init__.py`
- `backend/app/services/evidence_engine/__init__.py`
- `backend/app/api/router.py`
- `backend/requirements.txt`

## Models reused

- `ResearchSource`
- `SourceVersion`
- `Citation`
- `ClaimCitation`
- `Claim`
- `EvidencePassage`
- `Embedding`

No separate evidence or embedding database system was created.

## Database migration

`20261119_0006_phase9_evidence_embeddings.py` adds:

- Claim and evidence location fields to `evidence_passages`
- Abstract/full-text content classification
- Extraction method, source URL, DOI, and passage hash
- Claim embeddings to `embeddings`
- Nullable evidence-passage embedding ownership and claim ownership
- Foreign-key and uniqueness constraints

Live Alembic/PostgreSQL execution was not performed.

## APIs implemented

- `POST /api/v1/claims/{claim_id}/extract-evidence`
- `GET /api/v1/claims/{claim_id}/evidence`
- `GET /api/v1/sources/{source_id}/evidence`
- `POST /api/v1/documents/{document_id}/extract-evidence`
- `GET /api/v1/documents/{document_id}/evidence`

All endpoints use existing authentication dependencies and ownership verification.

## Embedding configuration

- Model: `sentence-transformers/all-MiniLM-L6-v2`
- Dimension: 384
- Storage: existing pgvector `Embedding.vector`
- Processing: lazy model loading and batch encoding
- Dimension mismatches raise an explicit runtime error rather than changing dimensions silently

## Evidence extraction methods

- Abstract extraction from `ResearchSource.abstract`
- HTML parsing with the Python standard library
- XML parsing with `xml.etree.ElementTree`
- PDF text extraction with PyMuPDF
- Legitimately accessible URL fetching through `httpx`
- Paragraph-preserving chunking with sentence-aware splitting
- Passage SHA-256 deduplication

Full text is not inferred from an abstract.

## Tests

Executed:

- Complete backend suite: 142 passed, 0 failed, 0 skipped
- Targeted evidence suite: passed
- HTML/XML parsing
- In-memory PDF extraction
- Chunking and scientific terminology/numerical preservation
- Chunk deduplication
- Mocked embedding generation
- Embedding dimension rejection
- Cosine similarity
- SQLite evidence persistence

Mocked provider and model behavior is not live source validation.

## Tests not executed

- Live PostgreSQL and pgvector write/read
- Live Sentence Transformers model download and inference
- Live Crossref/OpenAlex integration
- Real authenticated publication URL downloads
- Real academic full-text extraction
- Live paywall/access-restriction behavior
- Live cross-user API denial

## Known limitations

- Full-text availability depends on the source URL and provider response.
- HTML content removal is heuristic and may omit some structured publication sections.
- PDF extraction quality depends on the source document and embedded text.
- Image-only publications require OCR, which is outside this phase.
- Semantic ranking does not classify support or contradiction.
- Claim embeddings are stored only when model inference succeeds.

## Outstanding live validation

Live PostgreSQL, pgvector, Hugging Face model loading, real source pages, and real publication
documents remain outstanding for final validation.

## Phase 10 dependencies

Phase 10 may consume:

- Exact `EvidencePassage` text
- Source and DOI metadata
- Abstract versus full-text content type
- Passage location metadata
- Semantic similarity scores
- Reused `Claim`, `Citation`, and `ResearchSource` relationships
