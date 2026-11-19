# ANVEXA AI Deployment Guide

## Local build

Backend:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

Frontend:

```powershell
cd frontend
npm install
npm run dev
npm run build
```

## Frontend environment

Copy `frontend/.env.example` to `frontend/.env.local` and set:

```dotenv
VITE_API_BASE_URL=https://your-api.example.com/api/v1
```

Never put private API keys or database credentials in Vite variables.

## Backend environment

Copy `backend/.env.example` to `backend/.env` and set private values for:

- `ANVEXA_DATABASE_URL`
- `ANVEXA_JWT_SECRET_KEY`
- `ANVEXA_GEMINI_API_KEY`
- `ANVEXA_CORS_ORIGINS`
- Provider URLs and retry settings

Before starting in production, enable pgvector and apply migrations:

```powershell
.\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini upgrade head
```

Do not use SQLite or reset the database for production.

## Health and startup

Public health endpoint:

- `GET /health`
- `GET /api/v1/health/database`

The application factory is `backend.app.main:app`.

## Render-compatible backend

Use the repository root and install:

```text
pip install -r backend/requirements.txt
uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT
```

Set PostgreSQL with pgvector and all backend environment variables in Render.

## Vercel-compatible frontend

Set `VITE_API_BASE_URL` to the deployed backend `/api/v1` URL. Configure the Vite build:

- Build command: `npm run build`
- Output directory: `dist`
- Framework: Vite

Configure SPA rewrite/fallback to `/index.html`.

## CORS

Set:

```dotenv
ANVEXA_CORS_ORIGINS=["https://your-frontend.example.com"]
```

No wildcard origin should be used with authenticated browser requests.

## Deployment status

This repository prepares deployment configuration only. No platform deployment or secret provisioning
was performed.
