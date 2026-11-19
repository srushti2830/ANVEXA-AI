# ANVEXA AI

ANVEXA AI is an academic document verification platform. Backend development is
being delivered in phases; Phases 1 and 2 provide the FastAPI and PostgreSQL
foundations.

## Backend foundation

- Python 3.11 or newer
- FastAPI application factory and OpenAPI documentation
- Environment-based application settings
- `GET /health`
- PostgreSQL connection/session management with SQLAlchemy 2.0
- Alembic migrations and a pgvector-backed 384-dimensional embedding column
- Focused API, model, and CRUD tests

Authentication, document processing, and AI integrations are not part of these
phases.

## Database setup

Install PostgreSQL with the pgvector extension available, then set
`ANVEXA_DATABASE_URL` in `backend\.env` (copy `backend\.env.example` first).
The database user must be allowed to create the `vector` extension for the
initial migration, or an administrator can enable it before the migration.

From the repository root, apply the schema with:

```powershell
.\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini upgrade head
```

Schema changes are managed by Alembic; the application does not create tables
on startup. The initial schema includes the academic verification entities,
review and audit records, processing jobs, and a cosine HNSW index over
384-dimensional `sentence-transformers/all-MiniLM-L6-v2` embeddings.

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

Run the backend tests from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests
```

Do not put credentials in source control. Local `.env` files are ignored by
Git; only non-secret example configuration is tracked.
