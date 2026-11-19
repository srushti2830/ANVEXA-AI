# ANVEXA AI backend

The backend uses FastAPI, SQLAlchemy 2.x, PostgreSQL, pgvector, Alembic, and
Psycopg 3. This phase establishes database infrastructure only; it does not
implement authentication, document processing, or AI verification.

## Requirements

- Python 3.11 or newer
- PostgreSQL 14 or newer
- pgvector installed for the PostgreSQL server version in use

On Windows, install PostgreSQL using its official installer. pgvector must be
installed separately and must match the installed PostgreSQL major version and
architecture. Use a trusted prebuilt package or build pgvector using the
PostgreSQL development tools. PostgreSQL's `bin` directory must be available to
Psycopg if the installed Psycopg wheel requires system `libpq`.

## Create and configure the database

Create the database from PowerShell or a PostgreSQL shell:

```powershell
psql -U postgres -c "CREATE DATABASE anvexa_db;"
```

Install/enable pgvector in that database:

```powershell
psql -U postgres -d anvexa_db -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

The initial Alembic migration also runs `CREATE EXTENSION IF NOT EXISTS vector`.
If the application database role cannot create extensions, have a PostgreSQL
administrator run the command above first.

Copy `backend\.env.example` to `backend\.env` and set a private password:

```dotenv
ANVEXA_DATABASE_URL=postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5432/anvexa_db
ANVEXA_DATABASE_POOL_SIZE=5
ANVEXA_DATABASE_MAX_OVERFLOW=10
ANVEXA_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
ANVEXA_EMBEDDING_DIMENSION=384
```

The configured embedding model and dimension are validated together. Embeddings
are tagged with their model name, and semantic search only compares vectors
from the configured model. Changing to a model with a different dimension
requires a corresponding Alembic schema migration. No embeddings are generated
by the database phase.

Never commit `backend\.env` or put database credentials in source control.

## Install and migrate

From the repository root in PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
Copy-Item backend\.env.example backend\.env
```

Edit `backend\.env`, then apply and inspect migrations:

```powershell
.\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini upgrade head
.\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini current
```

Create future revisions only after changing SQLAlchemy models:

```powershell
.\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini revision --autogenerate -m "describe schema change"
```

Review generated migrations before applying them. The application does not run
`Base.metadata.create_all()` or connect to PostgreSQL during module imports.
Alembic is the production schema management path.

## Verify the database

Start the API:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload
```

Then check the database and pgvector:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health/database
psql -U postgres -d anvexa_db -c "SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';"
psql -U postgres -d anvexa_db -c "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;"
```

The database health endpoint reports connection and extension status without
returning a connection string or database error details. It returns HTTP 503
when the connection fails or pgvector is not available.

## Tests

Run the isolated unit test suite:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests
```

The CRUD/model tests use temporary SQLite databases and never drop or modify the
development database. Alembic's PostgreSQL DDL can be rendered without applying
it to a server:

```powershell
$env:ANVEXA_DATABASE_URL = "postgresql+psycopg://user:password@localhost:5432/anvexa_db"
.\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini upgrade head --sql
Remove-Item Env:\ANVEXA_DATABASE_URL
```

## Troubleshooting

- **Connection refused:** confirm the PostgreSQL service is running and the
  host/port in `ANVEXA_DATABASE_URL` are correct.
- **Database does not exist:** create `anvexa_db` before applying migrations.
- **Extension is unavailable:** install pgvector for the same PostgreSQL
  version/architecture, then run `CREATE EXTENSION vector` as an administrator.
- **Permission denied for extension:** ask a database administrator to enable
  pgvector in `anvexa_db`; the application role still needs schema privileges
  for ordinary migrations.
- **Psycopg cannot load its native library on Windows:** install the approved
  Psycopg binary wheel or make the matching PostgreSQL `libpq` available to
  Python, then restart the terminal.
