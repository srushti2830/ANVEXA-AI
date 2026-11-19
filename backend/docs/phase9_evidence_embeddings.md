# Phase 9 - Evidence Extraction and Embedding Engine

## Implemented workflow

1. Read Phase 8 `ResearchSource` records and linked `Citation` rows.
2. Use `ResearchSource.abstract` for clearly labeled abstract evidence.
3. Attempt legitimately accessible source URLs for HTML, XML, or PDF full text.
4. Chunk text into paragraph-preserving units without splitting short sentences.
5. Persist source passages in `EvidencePassage`.
6. Generate and validate 384-dimensional vectors with the existing configured Sentence Transformers model.
7. Persist vectors in `Embedding`.
8. Retrieve and rank evidence for claims with cosine similarity.

Abstract evidence is never labeled as full text. Similarity is returned only as semantic ranking and is
not a support or contradiction verdict.

## Source location preservation

Evidence passages retain source ID, source URL, DOI, section name, page number, paragraph number,
extraction method, passage hash, and exact extracted passage text.

## Embedding model

The existing configured model is `sentence-transformers/all-MiniLM-L6-v2`, with 384 dimensions.
The model is loaded lazily and dimensions are checked before database persistence. Identical passages
and existing embeddings are not regenerated.

## API testing

- `POST /api/v1/claims/{claim_id}/extract-evidence`
- `GET /api/v1/claims/{claim_id}/evidence`
- `GET /api/v1/sources/{source_id}/evidence`
- `POST /api/v1/documents/{document_id}/extract-evidence`
- `GET /api/v1/documents/{document_id}/evidence`
