# Phase 8 - Research Source Retrieval

## Workflow

1. Authenticate and verify document ownership.
2. Verify that the document is parsed and use its latest `DocumentVersion`.
3. Inspect `Citation` rows marked as bibliography/reference entries.
4. Prefer exact DOI lookup through Crossref, then OpenAlex for DOI identities.
5. Fall back to a bibliographic query through Crossref.
6. Deduplicate global `ResearchSource` rows by DOI or exact title/year.
7. Create a `SourceVersion` snapshot with a SHA-256 metadata fingerprint.
8. Link the matching `Citation.research_source_id` to the retrieved source.

No source full text, evidence passage, verification verdict, or claim-support result is generated.

## Provider behavior

- Crossref is used for DOI resolution and bibliographic fallback.
- OpenAlex is used as a DOI metadata fallback.
- Provider calls use bounded retries and a timeout.
- No result means `RetrievalStatus.UNAVAILABLE` is not fabricated; references remain unlinked.
- HTTP/provider failures are logged without exposing provider exceptions or credentials.

## Data persistence

The existing `ResearchSource`, `SourceVersion`, and `Citation.research_source_id` relationships are reused.
DOI rows are deduplicated globally. Exact title-plus-year rows are deduplicated as an additional
conservative fallback. Source versions are deduplicated by the provider metadata fingerprint.

## API testing

Authorize in Swagger, then call:

- `POST /api/v1/documents/{document_id}/retrieve-sources`
- `GET /api/v1/documents/{document_id}/sources?page=1&per_page=20`
- `GET /api/v1/sources/{source_id}`
- `GET /api/v1/claims/{claim_id}/sources`

Configure retrieval timeout and retries with `ANVEXA_SOURCE_RETRIEVAL_TIMEOUT_SECONDS` and
`ANVEXA_SOURCE_RETRIEVAL_MAX_RETRIES`. Providers require no API key for the public endpoints used.
