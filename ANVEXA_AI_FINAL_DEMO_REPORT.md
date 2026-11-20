# ANVEXA AI Final Demo Report

**Assessment date:** 2026-11-20
**Status:** Local development demo verified; **not production-ready**

## Start the application

Run these commands from the project root in two PowerShell terminals:

**Backend**

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

**Frontend**

```powershell
Set-Location frontend
npm run dev -- --host 127.0.0.1 --port 5173
```

## Demo entry and journey

- Frontend: [http://127.0.0.1:5173/](http://127.0.0.1:5173/)
- Backend health: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)
- Direct demo: [http://127.0.0.1:5173/demo/dashboard](http://127.0.0.1:5173/demo/dashboard)
- Entry is available from **Enter prepared demo** on the landing page and **Explore the prepared demo without an account** on the sign-in page.

The walkthrough is: dashboard → prepared illustrative document → six claims and evidence passages → citation/source mappings → prepared verification → human review submission → report preview and JSON export. The report page also has **Print / Save as PDF** for the browser's native print-to-PDF flow.

The required notice appears throughout the demo:

> DEMO MODE — Prepared demonstration data. Live database and external provider integrations are not active.

## What is prepared versus live

- Demo data is deterministic and in `frontend/src/demoFixtures.json`. The academic-style document, citation markers, source records, evidence passages, and verdicts are all synthetic illustrative fixtures—not publications, quotations, or real citations. No DOI, author, or real paper metadata is invented.
- The six verdict examples are present: `SUPPORTED`, `PARTLY_SUPPORTED`, `UNSUPPORTED`, `CONTRADICTORY`, `POSSIBLY_OUTDATED`, and `NEEDS_REVIEW`. Limitations explicitly state that missing evidence is not proof of falsehood.
- The verification action displays prepared results only. It does not call Gemini, a research provider, or the backend.
- A submitted sample review is stored in this tab's namespaced `sessionStorage`; **Exit demo** clears only the demo keys. No production auth tokens or database records are created.
- This prepared document is rendered as text; no PDF upload, parsing, or extraction from a real paper takes place in demo mode.
- JSON report data is generated as a browser Blob. Its payload was inspected and contained six verdicts and the submitted sample review. The browser automation did not capture a filesystem download event. The PDF action presents the browser-native print/save flow; an actual PDF file was not generated during validation.

## Validation evidence

| Check | Result | Evidence |
|---|---|---|
| Landing and sign-in demo entry | PASS | Browser found both development-only entry links and entered the dashboard from the landing page. |
| Prepared document and claims | PASS | Browser rendered the synthetic document and all 6 prepared claims/evidence records. |
| Citation/source explorer | PASS | Browser rendered 3 illustrative citation mappings and 2 synthetic source records. |
| Demo verification | PASS | Browser displayed all 6 required verdict categories with explanations and limitations. |
| Human review | PASS | Browser submitted one sample review and showed it in the prepared report. |
| Report preview / JSON payload | PASS | Report preview showed all verdicts; JSON Blob parsed with 6 verdicts and 1 review. |
| Print-to-PDF | NOT TESTED | Print/save control is present; no actual PDF file was saved. |
| Browser errors / backend isolation | PASS | Fresh-browser journey had no page or console errors and made zero requests to port 8000 from demo routes. |
| Protected production workspace | PASS | Unauthenticated `/app/dashboard` redirected to `/login`; production auth flow was not changed. |
| Development-only production exclusion | PASS | Production build succeeded; demo disclaimer, entry, and storage-key strings were absent from the generated JS bundle. |
| Frontend production build | PASS | `npm run build` completed. Vite emitted non-fatal React Router `use client` directive notices. |
| Backend regression suite | PASS | `.\.venv\Scripts\python.exe -m pytest backend\tests` — 189 passed. |
| Frontend HTTP | PASS | `GET http://127.0.0.1:5173/` returned HTTP 200. |
| Backend public health | PASS | `GET http://127.0.0.1:8000/health` returned HTTP 200. |
| Database-dependent features | BLOCKED | `GET http://127.0.0.1:8000/api/v1/health/database` returned HTTP 503; managed database is not configured. |

## Remaining limitations

- Demo mode is development-only (`import.meta.env.DEV`). It is not available in the production bundle.
- The demo is a frontend presentation path, not a substitute for registration, authentication, PostgreSQL persistence, live document processing, Gemini verification, research retrieval, or production review.
- The backend was started for validation, but database-backed APIs remain unavailable. Do not present this as a live end-to-end research result.
- Deployment and production readiness were not tested or claimed.
