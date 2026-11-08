# Continuum

**Agentic Project Continuity Platform** — reconstruct project knowledge from authorised sources so a handover survives the people who leave.

> **People may leave. The knowledge shouldn't have to.**

Built for **CodeZen India 2026 National Hackathon — Team Cipher**.

Workflow: **CONNECT → RECONSTRUCT → VERIFY → REVIEW → HANDOVER**

This repository implements **Phase 1 (Foundation)** and **Phase 2 (Source Ingestion)** end-to-end: a real FastAPI + PostgreSQL backend, a real React/Vite/Tailwind frontend, real authentication, real file ingestion and a real GitHub integration boundary. **Phase 3 (the AI agents that extract, verify and write the handover) is NOT implemented** — only its typed contracts exist.

---

## 1. What works today

| Stage | Status |
| --- | --- |
| **CONNECT** — sign in, create a workspace, create a project, connect GitHub, upload documents | ✅ Implemented |
| **RECONSTRUCT** — normalised source library backed by real ingestion | ✅ Implemented (ingestion only; no AI reconstruction) |
| **VERIFY / REVIEW / HANDOVER** | ⛔ Phase 3 — not implemented |

Concretely:

- **Auth** — Supabase sign-in with server-side JWT verification (HS256 secret or project JWKS), protected frontend routes, per-request workspace/project membership checks. A clearly-labelled development token flow exists for local testing and is refused in production.
- **Workspaces & projects** — full CRUD with tenant isolation. A resource the caller cannot see returns **404**, never **403**, so tenancy is not leaked.
- **Uploads** — PDF (PyMuPDF), Markdown, TXT and ZIP with a 10-step pipeline: content-type sniffing by magic bytes, size limits, a secret scanner that redacts and never logs values, SHA-256 hashing and duplicate detection, plus zip-slip/path-traversal/expansion protection.
- **GitHub** — server-side OAuth, tokens Fernet-encrypted at rest and never exposed to browser JS, repo listing, detail view, and import of commits / issues / PRs / README / text files as normalised sources. REST only, pagination and rate-limit handling included. When credentials are absent the endpoints return a clearly-labelled 503 boundary, not fabricated data.
- **Dashboard** — every number is a live SQL aggregate. There are no static or seeded source records anywhere in the application.

---

## 2. Architecture

```
┌──────────────────────────┐        ┌──────────────────────────────────────────┐
│  frontend/  (Vite SPA)   │  HTTPS │  backend/  (FastAPI)                     │
│  React 18 · TS · Tailwind│ ─────► │  routers → services → repositories → ORM  │
│  TanStack Query · Axios  │  JWT   │  Pydantic v2 · SQLAlchemy 2 · Alembic     │
│  Supabase JS (auth only) │        │  PyMuPDF · PyGithub · Fernet              │
└──────────────────────────┘        └───────────────────┬──────────────────────┘
                                                         │ SQLAlchemy / psycopg3
                                             ┌───────────▼───────────┐
                                             │  PostgreSQL 16        │
                                             │  + pgvector extension │
                                             └───────────────────────┘
```

- The backend **never** trusts a user id, workspace id or role from the client. Identity comes from the verified token; authorisation is re-derived from the database on every request.
- Every failing endpoint returns one stable error envelope: `{"error": {"code","message","details"}}`.
- The frontend has **one** Axios instance (`src/services/api.ts`) that attaches the JWT and emits a `continuum:unauthorized` event on 401. No permissions or validation live in the frontend.
- Uploaded files are **stored, never executed**.

Full endpoint reference: [docs/API.md](docs/API.md). Entity + claim/verification contracts: [docs/SCHEMAS.md](docs/SCHEMAS.md).

---

## 3. Repository layout

```
continuum/
├── backend/                 FastAPI application
│   ├── app/
│   │   ├── api/v1/          routers: health, auth, workspaces, projects, dashboard, sources, github
│   │   ├── core/            settings, security, errors, permissions, dependencies
│   │   ├── db/              engine, session, declarative base
│   │   ├── models/          SQLAlchemy 2 ORM models (8 core entities + 2 integration tables)
│   │   ├── repositories/    data access
│   │   ├── schemas/         Pydantic v2 request/response + Phase 3 contracts
│   │   ├── services/        business logic (ingestion, github, workspace, project, audit)
│   │   └── utils/           files, hashing, text
│   ├── alembic/             migrations
│   ├── tests/               pytest suite (real PostgreSQL)
│   ├── alembic.ini
│   └── requirements.txt
├── frontend/                React + Vite SPA
│   └── src/
│       ├── app/             router + providers
│       ├── components/      ui/ (shadcn-style) · common/ · layout/
│       ├── contexts/        AuthContext
│       ├── hooks/           TanStack Query hooks
│       ├── lib/             api client, query keys, formatting
│       ├── pages/           10 pages
│       ├── routes/          route guards
│       ├── services/        typed API calls
│       └── types/           shared TS interfaces
├── docker/init/             Postgres init (CREATE EXTENSION vector, uuid-ossp)
├── docs/                    API.md · SCHEMAS.md
├── docker-compose.yml       pgvector/pgvector:pg16
├── .env.example             every environment variable, documented
└── README.md
```

---

## 4. Prerequisites

- **Node.js 18+** and npm
- **Python 3.12+**
- **Docker** (only to run PostgreSQL locally)
- A **Supabase** project *or* the development token flow (§6)
- Optional: a **GitHub OAuth App** for repository import

---

## 5. Setup

### 5.1 Database

```bash
# from the repository root
docker compose up -d
```

This starts `pgvector/pgvector:pg16` as container **`continuum-db`**, mapped to host port **5433** (chosen so it never collides with a locally-installed PostgreSQL on 5432). The init script enables the `vector` and `uuid-ossp` extensions. Data persists in the `continuum_pgdata` volume.

Create the test database once:

```bash
docker exec continuum-db psql -U continuum -d continuum -c "CREATE DATABASE continuum_test;"
```

### 5.2 Environment variables

```bash
# from the repository root
cp .env.example .env            # backend reads .env / ../.env

# frontend
cp frontend/.env.example frontend/.env
```

Every variable is documented inline in [.env.example](.env.example). Summary:

| Variable | Scope | Required | Purpose |
| --- | --- | --- | --- |
| `DATABASE_URL` | backend | ✅ | `postgresql+psycopg://continuum:continuum@localhost:5433/continuum` |
| `CORS_ORIGINS` | backend | ✅ | Comma-separated allowed frontend origins |
| `ENVIRONMENT` | backend | ✅ | `development` \| `staging` \| `production` |
| `SUPABASE_URL` | backend | Supabase mode | Project URL |
| `SUPABASE_JWT_SECRET` | backend | Supabase mode (HS256) | JWT secret; omit to verify via JWKS (RS256) |
| `SUPABASE_JWT_AUDIENCE` | backend | – | Default `authenticated` |
| `SUPABASE_SERVICE_ROLE_KEY` | backend | – | Server-side only |
| `ALLOW_DEV_AUTH` | backend | local dev | Enable the static dev token. **Must be `false` in production.** |
| `DEV_AUTH_TOKEN` | backend | local dev | Must match the frontend's `VITE_DEV_AUTH_TOKEN` |
| `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` | backend | GitHub | OAuth App credentials |
| `GITHUB_TOKEN_ENCRYPTION_KEY` | backend | GitHub | Fernet key: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `GITHUB_OAUTH_REDIRECT_URI` | backend | GitHub | Must match the OAuth App callback |
| `GITHUB_OAUTH_FRONTEND_REDIRECT` | backend | GitHub | Where the browser lands after callback |
| `MAX_UPLOAD_SIZE_BYTES` | backend | – | Default 25 MB |
| `MAX_ZIP_EXPANSION_BYTES` | backend | – | Default 100 MB |
| `UPLOAD_DIR` | backend | – | Default `./storage/uploads` |
| `VITE_API_BASE_URL` | frontend | ✅ | `http://localhost:8000/api/v1` |
| `VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY` | frontend | Supabase mode | Public anon key only — **never** a secret |
| `VITE_DEV_AUTH_TOKEN` | frontend | local dev | Must match `DEV_AUTH_TOKEN` |

> `VITE_*` values are shipped to the browser. Never put a server secret behind a `VITE_` prefix.

### 5.3 Backend

```bash
cd backend
python -m venv .venv
# Windows
.\.venv\Scripts\Activate.ps1
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

- API: <http://localhost:8000/api/v1>
- Swagger: <http://localhost:8000/docs>
- Liveness: <http://localhost:8000/health> · Readiness: <http://localhost:8000/health/ready>

### 5.4 Frontend

```bash
cd frontend
npm install
npm run dev
```

App: <http://localhost:5173>

---

## 6. Local authentication testing

The backend verifies Supabase JWTs in production. For local end-to-end testing without a Supabase project, a **development-only** bypass is available:

1. In the backend `.env`, set:
   ```
   ENVIRONMENT=development
   ALLOW_DEV_AUTH=true
   DEV_AUTH_TOKEN=dev-local-token
   ```
2. In `frontend/.env`, set the matching value:
   ```
   VITE_DEV_AUTH_TOKEN=dev-local-token
   ```
3. Start both services. `GET /health/ready` reports `"dev_auth_enabled": true`, and the Login page exposes a clearly-labelled **"Continue with development session"** button.

This path is refused whenever `ENVIRONMENT=production`, regardless of `ALLOW_DEV_AUTH`. It is a local-testing affordance, **not** a substitute for real authentication.

To use Supabase instead, fill in `SUPABASE_URL` + `SUPABASE_ANON_KEY` (frontend) and `SUPABASE_JWT_SECRET` or `SUPABASE_URL` (backend) and sign in normally.

---

## 7. Tests

Both suites use synthetic data and talk to real infrastructure — no mocked persistence.

```bash
# Backend — requires the continuum_test database (see §5.1)
cd backend
.\.venv\Scripts\python.exe -m pytest          # or: python -m pytest
# → 69 passed, 1 warning

# Frontend — type-check, unit/component tests, production build
cd frontend
npm run typecheck     # tsc --noEmit
npm test              # vitest run  → 44 passed across 9 files
npm run build         # tsc --noEmit && vite build
```

Backend coverage areas: health/readiness, auth provisioning, workspace isolation, project CRUD + role enforcement, uploads (valid, oversize, wrong type, denied names, ZIP safety), parsers, the secret scanner, the GitHub boundary, dashboard aggregates, and the claim/verification contract (including an assertion that an agent **cannot** set `Verified`).

Frontend coverage areas: API error mapping, formatting/source-metadata helpers, shared states, route guards, and the Dashboard / Source Library / Upload / Login pages.

---

## 8. Scope

### Phase 1 — Foundation ✅
Monorepo, 8-entity schema with UUID PKs/indexes/FKs, Alembic migrations, pgvector provisioned, Supabase Auth with backend JWT verification and server-side role/workspace checks, workspace & project APIs, and the central typed API client with TanStack Query hooks.

### Phase 2 — Source Ingestion ✅
PDF/Markdown/TXT/ZIP upload with the 10-step pipeline, secret scanning and redaction, normalisation engine, hash-based dedupe, GitHub OAuth + repository/commit/issue/PR/README/file import, and the source library UI.

### Phase 3 — AI agents ⛔ (not implemented)
Claim extraction (Extractor), evidence verification (Verifier) and handover generation (Handover Writer) with LangGraph + the Gemini adapter. The typed contracts exist in `backend/app/schemas/claim.py` / `evidence.py` and are documented in [docs/SCHEMAS.md](docs/SCHEMAS.md).

**Governance rule, enforced in code:** only a human reviewer may set a claim to **`Verified`**. The AI layer may only ever emit `Supported`, `Uncertain` or `Conflict`; `assert_ai_assignable_status()` raises if an automated pipeline attempts anything else.

### Not yet done / known limitations

- No AI/LLM calls are made anywhere in the codebase.
- No embeddings or vector columns are defined (the extension is provisioned only).
- GitHub import is limited to the REST API; `include_changed_files` costs an extra request per record and is off by default.
- Supabase sign-up email confirmation flow is configured on the Supabase side, not in this repository.
- The production Vite bundle exceeds 500 kB in one chunk (a warning, not an error).

---

## 9. Deployment notes

- **Frontend → Vercel.** Set `VITE_API_BASE_URL`, and the Supabase/`VITE_DEV_AUTH_TOKEN` variables as needed. Server secrets must **not** be set here.
- **Backend → Render (or equivalent).** Set `DATABASE_URL`, `CORS_ORIGINS` (include the Vercel origin), `ENVIRONMENT=production`, and the Supabase/GitHub variables. Run `alembic upgrade head` as a release step. `ALLOW_DEV_AUTH` must be `false`.
- **Database → Supabase Postgres or a managed PostgreSQL with the `vector` extension.** Run `alembic upgrade head` and ensure `CREATE EXTENSION vector` is permitted.
- All credentials are supplied via environment variables. Nothing is hard-coded and no secret is ever committed.

---

## 10. Documentation

- [docs/API.md](docs/API.md) — every endpoint, request/response shapes, roles, error codes.
- [docs/SCHEMAS.md](docs/SCHEMAS.md) — the entities, the Claim/Verification contracts, and the human-verification rule.
