# Phase 14 Integration Audit

## Frontend status

No React/Vite frontend existed before Phase 14. A new JavaScript React app was added under
`frontend/` using React Router, Axios, and organized CSS. It includes public landing/authentication,
protected dashboard/documents/claim/review/settings views, actual API actions, loading/error/empty
states, and responsive layouts.

## Backend status

FastAPI is available and includes authentication, documents, parsing, claims, citations, sources,
evidence, verification, verdict classification, human review, reports, analytics, health, and user
management routes. The backend suite is implemented and passed 183 tests locally.

## Registered route groups

- `/api/v1/auth/*`
- `/api/v1/users/*`
- `/api/v1/documents/*`
- `/api/v1/claims/*`
- `/api/v1/sources/*`
- `/api/v1/reviews/*`
- `/api/v1/analytics/*`

All major route groups are already registered in `app/api/router.py`.

## Schema mismatches and integration assumptions

- Claim detail is returned by `GET /api/v1/claims/{claim_id}`; it uses `claim_text`,
  `original_sentence`, page, section, citation, and extraction fields.
- Evidence detail uses `evidence_id`, `evidence_text`, `content_type`, and source metadata.
- Document report and claim report are distinct schema shapes.
- Source response metadata is serialized as `metadata` through Pydantic aliasing.
- Human review identity is always derived from the authenticated reviewer; client reviewer IDs are
  not accepted.
- The document workflow is sequential and reflects actual Phase 5–13 processing status.

## Missing or broken integrations

- Live PostgreSQL has not been configured or migrated in this environment.
- Live Gemini verification and live Crossref/OpenAlex retrieval were not executed.
- Live PDF/JSON downloads and live authentication were not executed.
- Celery/Redis background processing is not present and was not introduced.
- Reported migration constraint names should be verified against a real PostgreSQL upgrade.

## Authentication

JWT access and refresh tokens are required for protected endpoints. The frontend stores access and
refresh tokens in browser local storage and sends the access token in `Authorization: Bearer`.
Passwords are never persisted in frontend storage.

## CORS

Development CORS defaults allow `http://localhost:3000` and `http://127.0.0.1:3000`. Production
must set `ANVEXA_CORS_ORIGINS` to the deployed frontend origin.

## Database

PostgreSQL plus pgvector is required. Alembic revision chain has one head:
`20261119_0010`. Offline SQL rendering succeeded in setup tests; real PostgreSQL upgrade/downgrade
execution remains unverified.
