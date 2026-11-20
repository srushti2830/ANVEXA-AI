# ANVEXA AI Deployment Readiness Report

**Prepared:** 2026-11-20
**Status:** **READY FOR ACCOUNT-CONFIGURATION AND DEPLOYMENT** with public-deployment blockers
**Actual public deployment:** NOT performed
**Git push:** NOT performed
**Production data mutation:** NOT performed

## Current verified state

| Area | Result |
|---|---|
| Neon PostgreSQL | Connected and health HTTP 200 locally |
| pgvector | Available |
| Alembic | Migration chain used successfully through 0011 |
| Backend tests | 206 passed, 5 skipped |
| Frontend production build | Passed |
| Crossref | Live DOI lookup passed |
| OpenAlex | Live DOI lookup passed |
| Europe PMC | Live DOI lookup passed |
| Semantic Scholar | Application integration present; live provider currently HTTP 429 |
| Gemini | **BLOCKED**: no key is loaded into settings |
| Evidence processing | Live API completed in 8.37 seconds |
| Human review and reports | Live and persisted locally |
| Public deployment | Not performed |

## Render backend configuration

Existing [render.yaml](render.yaml) is configured for:

- Runtime: Python
- Root: `backend`
- Build: `pip install -r requirements.txt`
- Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Health check: `/health`
- Pre-deploy migration: `alembic upgrade head`

The pre-deploy migration may require `alembic.ini` and environment variables to be available at release time. Render must receive a PostgreSQL URL that uses `postgresql+psycopg://` and Neon SSL parameters.

### Required Render environment variables

| Variable | Value/source | State |
|---|---|---|
| `ANVEXA_ENVIRONMENT` | `production` | Configured in YAML |
| `ANVEXA_API_V1_PREFIX` | `/api/v1` | Configured in YAML |
| `ANVEXA_DATABASE_URL` | Neon `postgresql+psycopg://...?...sslmode=require` | Manual secret required |
| `ANVEXA_JWT_SECRET_KEY` | Random value of at least 32 characters | Render generate/secret required |
| `ANVEXA_GEMINI_API_KEY` | Gemini API key | Manual secret required |
| `ANVEXA_CORS_ORIGINS` | `https://www.anvexa.ai` | Manual secret/config required |
| `ANVEXA_OBJECT_STORAGE_BACKEND` | `s3` | Configured in YAML |
| `ANVEXA_S3_BUCKET` | S3-compatible bucket name | Manual secret required |
| `ANVEXA_S3_REGION` | AWS region, or provider region if applicable | Manual secret required |
| `ANVEXA_S3_ENDPOINT_URL` | Required for R2/MinIO-compatible provider; blank for AWS S3 | Manual value required |
| `ANVEXA_S3_ACCESS_KEY_ID` | Object-store access key | Manual secret required |
| `ANVEXA_S3_SECRET_ACCESS_KEY` | Object-store secret key | Manual secret required |
| `ANVEXA_S3_PREFIX` | `anvexa/documents` | Configured in YAML |

Optional provider settings:

- `ANVEXA_CROSSREF_API_URL=https://api.crossref.org`
- `ANVEXA_OPENALEX_API_URL=https://api.openalex.org`
- `ANVEXA_SEMANTIC_SCHOLAR_API_URL=https://api.semanticscholar.org`
- `ANVEXA_EUROPE_PMC_API_URL=https://www.ebi.ac.uk/europepmc/webservices/rest`

Do not set `ANVEXA_DEV_DATABASE_MODE=true` or a SQLite URL in production.

## Render health and migration validation

Expected endpoints:

- `GET /health` → HTTP 200
- `GET /api/v1/health/database` → HTTP 200 with pgvector `available`
- `GET /docs` → Swagger available, expected for controlled public access

The intended migration command is:

```powershell
alembic upgrade head
```

Migration execution must occur only after the Neon production database connection and `vector` permission are confirmed. The repository migration chain is not to be reset or deleted.

## Vercel frontend configuration

Existing [vercel.json](frontend/vercel.json) preserves SPA refresh routing.

Required Vercel environment variable:

| Variable | Required value |
|---|---|
| `VITE_API_BASE_URL` | `https://YOUR_RENDER_SERVICE.onrender.com/api/v1` |

The frontend production build now fails explicitly when `VITE_API_BASE_URL` is missing. The `.env.example` contains no localhost URL.

Recommended build settings:

- Framework: Vite
- Root: `frontend`
- Install: `npm install`
- Build: `npm run build`
- Output: `dist`

## Document storage

The application no longer silently treats local filesystem storage as production-ready. Production startup requires:

- `ANVEXA_OBJECT_STORAGE_BACKEND=s3`
- `ANVEXA_S3_BUCKET`
- S3-compatible credentials

An S3-compatible backend is implemented in [s3_storage.py](backend/app/services/document_storage/s3_storage.py). It:

- Stores objects under the configured key prefix.
- Uses server-side AES256 encryption.
- Supports AWS S3 and custom endpoints.
- Prevents path traversal.
- Is excluded from current test credentials.

Render local disk is not suitable as the sole production document store because it is ephemeral across redeploy/restart.

## Security readiness

Verified or prepared:

- `.env` files are ignored and are not tracked.
- A source-controlled JWT fallback was removed.
- JWT and refresh tokens use the configured secret.
- Cross-user document access is denied.
- Reviewer role authorization is enforced.
- Production settings reject SQLite.
- Production settings reject local object storage.
- CORS must be restricted to `https://www.anvexa.ai`.
- Upload validation checks extension, MIME/magic bytes and 50 MB size limit.
- Storage keys sanitize path traversal.

Remaining security actions:

- Generate a unique production JWT secret outside source control.
- Do not reuse development Neon credentials or test accounts.
- Set Gemini and S3 credentials only in Render/Vercel dashboard secrets.
- Confirm Neon role permissions for ordinary schema writes and pgvector use.
- Optionally restrict OpenAPI/docs exposure if public API documentation is undesired.

## Manual account actions

1. Create or confirm the public DNS/Vercel deployment for `https://www.anvexa.ai`.
2. Supply the Render service URL.
3. Supply the Neon production database URL.
4. Supply a strong JWT secret.
5. Supply `ANVEXA_GEMINI_API_KEY`.
6. Create an S3 or S3-compatible bucket and credentials.
7. Set the exact Render environment variables.
8. Set `VITE_API_BASE_URL` in Vercel.
9. Deploy frontend and backend only after the owner approves.

## Final public verification checklist

1. Verify Render `/health` and `/api/v1/health/database`.
2. Verify migrations and tables on intended Neon database.
3. Verify `https://www.anvexa.ai` opens and refresh routing works.
4. Register a dedicated public test account.
5. Login and confirm access/refresh JWT behavior.
6. Upload a synthetic DOCX.
7. Parse, extract claims and detect citations.
8. Retrieve Crossref/OpenAlex/Europe PMC metadata.
9. If Gemini credentials work, execute live claim extraction and evidence-grounded verification.
10. Confirm evidence IDs exist and no missing evidence is classified as false.
11. Submit a human review.
12. Download PDF and JSON reports.
13. Restart backend and verify Neon and object-storage persistence.

## Validation status

- **Backend tests:** PASS — 206 passed, 5 skipped.
- **Frontend build:** PASS.
- **Local database health:** PASS.
- **Provider live integration:** PASS for Crossref, OpenAlex and Europe PMC; Semantic Scholar limited by HTTP 429.
- **Gemini live integration:** BLOCKED until key and live test execution.
- **Public deployment:** NOT TESTED.
- **Object storage account:** BLOCKED until bucket and credentials are supplied.
- **Final public status:** NOT DEPLOYED.
