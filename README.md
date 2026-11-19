# ANVEXA AI

ANVEXA AI is an academic document verification platform. Backend development is
being delivered in phases; this repository currently contains the Phase 1
FastAPI foundation only.

## Backend foundation

- Python 3.11 or newer
- FastAPI application factory and OpenAPI documentation
- Environment-based application settings
- `GET /health`
- Focused health and OpenAPI tests

Database models, authentication, document processing, and AI integrations are
not part of Phase 1.

## Run locally (Windows PowerShell)

From the repository root:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
Copy-Item backend\.env.example backend\.env
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload
```

Open `http://127.0.0.1:8000/docs` for the generated API documentation or
`http://127.0.0.1:8000/health` for the health check.

Run the Phase 1 tests from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests
```

Do not put credentials in source control. Local `.env` files are ignored by
Git; only non-secret example configuration is tracked.
