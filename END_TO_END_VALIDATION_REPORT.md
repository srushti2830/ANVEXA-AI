# ANVEXA AI End-to-End Validation Report

**Validation date:** 2026-11-20
**Environment:** Local FastAPI backend connected to Neon PostgreSQL 18.7
**Test document:** A newly generated, clearly labelled synthetic academic DOCX. Its illustrative statement cites the real Crossref record for DOI `10.1038/sdata.2016.18`; the test document is not a publication and its text is not evidence.

## Results

| Stage | Endpoint / operation | HTTP | Result and persistence | Execution |
|---|---|---:|---|---|
| Database health | `GET /api/v1/health/database` | 200 | Neon PostgreSQL connected; pgvector reported available. | Live |
| Register | `POST /api/v1/auth/register` | 201 | Dedicated test user created in Neon. | Live |
| Login / identity | `POST /api/v1/auth/login`, `GET /api/v1/auth/me` | 200 / 200 | Login and authenticated identity succeeded. Passwords are stored as hashes. | Live |
| Upload | `POST /api/v1/documents/upload` | 201 | Test DOCX metadata and ownership persisted. | Live |
| Parse | `POST /api/v1/documents/{id}/parse` | 200 | One parsed page persisted; document reached `COMPLETED`. | Live |
| Claim extraction | `POST /api/v1/documents/{id}/extract-claims`, `GET /api/v1/documents/{id}/claims` | 200 / 200 | Two claims persisted and retrievable. Gemini was not configured; the existing rule-based extractor ran. | Live fallback; no Gemini result |
| Citation detection / mapping | `POST /api/v1/documents/{id}/detect-citations`, `GET /api/v1/documents/{id}/citations` | 200 / 200 | Two citations and two claim-citation mappings persisted. | Live |
| Source retrieval | `POST /api/v1/documents/{id}/retrieve-sources`, `GET /api/v1/documents/{id}/sources` | 200 / 200 | One Crossref record persisted for the real DOI `10.1038/sdata.2016.18`; title matched the Crossref metadata. | Live Crossref |
| Evidence extraction | `POST /api/v1/documents/{id}/extract-evidence` | Client timed out | The call exceeded the 180-second client timeout; the server nevertheless persisted evidence. A subsequent evidence read returned all seven passages. | Live; initial response timed out |
| Evidence retrieval | `GET /api/v1/documents/{id}/evidence` | 200 | Seven passages persisted and retrievable: six extracted from accessible HTML and one from the Crossref abstract. | Live |
| Embeddings | Sentence Transformers and Neon pgvector | N/A | Seven embeddings persisted; pgvector health remained available. | Live |
| Verification / classification | `POST /api/v1/documents/{id}/verify` | 200 | Two results persisted as `NEEDS_REVIEW`; zero completed AI verifications. No evidence was fabricated or treated as proof of falsity. | Live API; Gemini blocked |
| Human review | `GET /api/v1/reviews/queue`, `GET /api/v1/reviews/{id}`, `POST /api/v1/reviews/{id}/submit` | 200 / 200 / 200 | Reviewer submitted an honest `NEEDS_REVIEW` decision; one review-history row persisted. A second result remains pending. | Live |
| JSON report | `GET /api/v1/documents/{id}/report/json` | 200 | Valid JSON returned: two claims, one source, seven evidence passages, one human-reviewed claim. Report row persisted. | Live |
| PDF report | `GET /api/v1/documents/{id}/report/pdf` | 200 | Valid PDF signature; 2,611 bytes. Report row persisted. | Live |
| Cross-user authorization | `GET /api/v1/documents/{id}` as another registered user | 403 | Access to the owner’s document was denied. | Live |
| Restart persistence | Restart FastAPI; then login and read document, claims, evidence and reports | 200 | Existing records remained accessible from Neon after restart. | Live |

## Fixes made during validation

- Corrected the report source query: PostgreSQL cannot apply `DISTINCT` to the ORM row containing a `JSON` column. The redundant `DISTINCT` was removed because source IDs are deduplicated before querying.
- Corrected report evidence totals to include both claim-linked and source-linked passages. A focused regression test covers source-level evidence.
- Removed the source-controlled JWT secret fallback. `ANVEXA_JWT_SECRET_KEY` is now required and must be at least 32 characters. The example environment file leaves it blank, and Render is configured to generate a secret. A private random local key was added to ignored `backend/.env`; its value is not included here.

## Provider notes and blockers

- **Gemini:** Not configured in the local environment. Claim extraction therefore used the existing rule-based fallback. Verification safely persisted `NEEDS_REVIEW`; no Gemini response is claimed.
- **Crossref:** Used successfully by the application to retrieve real source metadata.
- **OpenAlex:** A direct service lookup succeeded in the preceding live integration check; Crossref supplied the source in this document workflow.
- **Semantic Scholar and Europe PMC:** Direct network probes succeeded in the preceding check, but neither provider is integrated into ANVEXA’s current source-retrieval service. They are not claimed as application retrieval results.
- **Evidence response latency:** The extraction POST exceeded the client timeout even though the operation completed and persisted its rows. The synchronous endpoint’s latency remains a reliability issue to address.

## Verification commands and outcome

- Backend: `python -m pytest tests -q` from `backend/` — **201 passed**.
- Frontend: `npm run build` from `frontend/` — **passed**.
- Focused report/JWT tests — **16 passed**.
- Backend was restarted with the configured local JWT key; database health and the post-restart API checks succeeded.

## Data-safety note

Validation created dedicated test accounts, a synthetic document, related records, and report rows in Neon. No existing records were deleted. The test account password was reset only for the test account to reauthenticate after the local JWT-key change. Uploaded documents and secrets remain local and are excluded from the intended source push.

## Overall status

**COMPLETE WITH LIMITATIONS.** Persistent upload, parsing, rule-based claim extraction, citation mapping, Crossref retrieval, evidence extraction, embedding persistence, safe `NEEDS_REVIEW` classification, human review, and PDF/JSON reporting were exercised. Gemini verification remains blocked by the missing API key; the evidence extraction endpoint also needs a latency improvement.
