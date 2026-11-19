# Phase 14 Integration Checklist

## Fixed issues

- [x] Vite development origin added to FastAPI CORS: `http://127.0.0.1:5173`.
- [x] Vite development API fallback changed to `http://127.0.0.1:8000/api/v1`.
- [x] Production API fallback uses same-origin `/api/v1` unless `VITE_API_BASE_URL` is set.
- [x] Frontend `.env.example` documents the development API base.
- [x] Access and refresh tokens moved from `localStorage` to tab-scoped `sessionStorage`.
- [x] Refresh-token handling reuses bearer-compatible refresh endpoint behavior.
- [x] Added source/citation explorer route and UI.
- [x] Added settings route.
- [x] Added success feedback only after successful backend mutations.
- [x] Added upload and workflow success feedback.
- [x] Added migration constraint regression coverage.
- [x] Corrected migration 0009 review-action constraint upgrade/downgrade names.
- [x] Corrected migration 0010 report-format constraint upgrade/downgrade names.
- [x] Verified migration 0009 and 0010 offline downgrade SQL.

## Remaining issues

- [ ] Live PostgreSQL/pgvector database must be configured.
- [ ] Live registration, login, refresh, logout and protected-route requests remain blocked.
- [ ] Live document workflow requires PostgreSQL and a real test document.
- [ ] Live Gemini verification credentials are unavailable.
- [ ] Live Crossref/OpenAlex retrieval credentials/network behavior are unverified.
- [ ] Live PDF/JSON download through FastAPI is untested.
- [ ] Browser end-to-end automation is not implemented.
- [ ] The safest refresh-token implementation is HttpOnly cookies, but existing backend currently accepts refresh tokens by JSON and would need a compatible cookie migration.

## Actual tests executed

- Complete pytest suite: **185 passed**.
- Focused migration tests: **3 passed**.
- Frontend production build: passed.
- Frontend preview/dev HTTP check: `200 OK`.
- Backend `/health`: `{"status":"ok"}`.
- Swagger `/docs`: `200 OK`.
- Live OpenAPI route discovery: 56 paths and 58 operations.
- CORS preflight for `http://127.0.0.1:5173`: allowed-origin header returned.
- PostgreSQL listener check: TCP port 5432 unavailable.
- Database health endpoint: HTTP 503, database unavailable.
- Live registration attempt: HTTP 503, database unavailable.
- Offline Alembic upgrade SQL: rendered through head `20261119_0010`.
- Offline Alembic downgrade 0009 range: rendered successfully.
- Offline Alembic downgrade 0010 range: rendered successfully.
- No live Gemini, research API or real-document execution was claimed.

## Tests not executed

- Live PostgreSQL persistence.
- Live migration upgrade/downgrade.
- Live JWT registration/login/refresh/logout.
- Live document upload and parsing.
- Live claim/citation/source/evidence/verification workflow.
- Live human review.
- Live report generation/download.
- Live Gemini API.
- Live Crossref/OpenAlex retrieval.
- Browser end-to-end test automation.
- Production deployment.
