# Phase 6 — Claim Extraction

## Workflow

1. Confirm the document belongs to the authenticated user and parsing is `completed`.
2. Read the latest `DocumentVersion` and its `DocumentPage` records; the original file is not reopened.
3. Segment each page into paragraph blocks and sentences, retaining page and paragraph locations.
4. Detect claims with Gemini when configured. Otherwise run the rule-based extractor.
5. Persist unique claims against the parsed version and return paginated results.
6. Reprocessing the same version returns the existing persisted extraction.

## Categories

Claims are classified as scientific, statistical, comparative, causal, methodological, medical,
technical, historical, general factual, descriptive, temporal, numerical, or other.

## Citation association

The engine records `[1]`, `[2, 4]`, author-year markers, named author markers, and DOI strings found
in the sentence or its paragraph. These markers are traceability metadata only. They do not assert
that a citation supports or verifies a claim.

## Confidence

`extraction_confidence` is a 0–1 estimate that the text is a factual, independently verifiable claim.
It is not a probability that the claim is true.

## Extraction methods

- `gemini`: the configured Gemini model returned Pydantic-validated JSON and exact original wording
  was matched to extracted document sentences.
- `rule_based`: deterministic language patterns ran because Gemini was unavailable or failed.

Gemini API failures use bounded retries and a timeout, then fall back transparently. Internal provider
errors and API keys are never returned to clients.

## Swagger testing

Authorize with a bearer token in `/docs`, then call:

1. `POST /api/v1/documents/{document_id}/extract-claims`
2. `GET /api/v1/documents/{document_id}/claims?page=1&per_page=20`
3. `GET /api/v1/claims/{claim_id}`

Configure Gemini with `ANVEXA_GEMINI_API_KEY`, optionally `ANVEXA_GEMINI_MODEL`,
`ANVEXA_GEMINI_TIMEOUT_SECONDS`, and `ANVEXA_GEMINI_MAX_RETRIES`.
