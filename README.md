# Continuum

**Agentic Project Continuity Platform** — reconstruct project knowledge from authorised sources so a handover survives the people who leave.

> **People may leave. The knowledge shouldn't have to.**

Built for **CodeZen India 2026 National Hackathon — Team Cipher**.

> [!IMPORTANT]
> ### 🏆 PUBLIC JUDGE ACCESS MODE — ZERO SIGN-IN DEMO
> Continuum is configured for frictionless evaluation by hackathon judges.
> **No sign-in, email, password, Supabase session, or GitHub OAuth is required to explore the product.**
> When accessed via the deployed URL or local root (`/`), judges immediately enter the **Public Demo Environment** loaded with a realistic synthetic workspace:
> - **Workspace:** `Continuum Demo Workspace`
> - **Project:** `Payment Gateway System` (Ground-truth synthetic architecture)
> - **Assets:** 8 normalised documentation/ADR sources, 28 verified/supported project memory claims, evidence spans, detected conflicts, an approved v1 handover snapshot, and an active 98.2% readiness evaluation.
> - **Guards:** Public demo endpoints are read-only by default to prevent data tampering, with tenant isolation (non-demo data returns 404) and a safe disposable demo reset button (`POST /api/v1/public/demo/reset`).

Workflow: **CONNECT → RECONSTRUCT → VERIFY → REVIEW → HANDOVER**

This repository implements **Phases 1–5** end-to-end: a real FastAPI + PostgreSQL + pgvector backend, a real React/Vite/Tailwind frontend, real authentication, real source ingestion, an AI reconstruction pipeline (LangGraph + a Gemini adapter) with human-governed verification, versioned handovers, and a **deterministic handover-readiness, successor-experience and evaluation layer**.

---

## 1. What works today

| Stage | Status |
| --- | --- |
| **CONNECT** — sign in, create a workspace, create a project, connect GitHub, upload documents | ✅ Implemented |
| **RECONSTRUCT** — normalised source library, claim extraction, evidence verification, conflict detection | ✅ Implemented (requires a configured model key — see §6) |
| **VERIFY** — evidence spans, verification verdicts, uncertainty centre | ✅ Implemented |
| **REVIEW** — review queue, approve/reject/clarify/edit, conflict resolution | ✅ Implemented |
| **HANDOVER** — versioned handover, approval workflow, Markdown/PDF export, audit trail | ✅ Implemented |
| **READINESS & SUCCESSOR EXPERIENCE** — deterministic readiness engine, successor workspace, checklist, knowledge risk, missing knowledge, continuity scorecard | ✅ Implemented |
| **EVALUATION** — synthetic ground truth, reproducible metrics A–I, run comparison, successor exercise | ✅ Implemented |

Highlights:

- **Auth** — Supabase sign-in with server-side JWT verification (HS256 secret or project JWKS), protected frontend routes, per-request workspace/project membership checks. A clearly-labelled development token flow exists for local testing and is refused in production.
- **Workspaces & projects** — full CRUD with tenant isolation. A resource the caller cannot see returns **404**, never **403**, so tenancy is not leaked.
- **Uploads** — PDF (PyMuPDF), Markdown, TXT and ZIP with a 10-step pipeline: content-type sniffing by magic bytes, size limits, a secret scanner that redacts and never logs values, SHA-256 hashing and duplicate detection, plus zip-slip/path-traversal/expansion protection.
- **GitHub** — server-side OAuth, tokens Fernet-encrypted at rest and never exposed to browser JS, repo listing, detail view, and import of commits / issues / PRs / README / text files as normalised sources. REST only, with pagination and rate-limit handling. When credentials are absent the endpoints return a clearly-labelled 503 boundary, not fabricated data.
- **Reconstruction** — a LangGraph workflow (`app/workflow/`) extracts claims, verifies each against its cited evidence and detects contradictions. **Only a human reviewer can set a claim to `Verified`**; the AI layer may only emit `Supported`, `Uncertain` or `Conflict` (`assert_ai_assignable_status()`). If `GEMINI_API_KEY` is unset, the reconstruction endpoints return 503 — nothing is faked.
- **Readiness (Phase 5)** — a **deterministic** engine (`readiness_service.py` + `readiness_catalog.py`). Requirements are *data*; completion is derived from **approved** claims, their evidence and open conflicts; the score is a pure function of the completions and configurable weights. An LLM never decides a score. Every evaluation stores the exact weights, requirement results and claim revisions used, so a score can be re-derived and audited.
- **Dashboard & scorecard** — every number is a live SQL aggregate. There are no static or seeded source records anywhere in the application.

---

## 2. Architecture

```
┌──────────────────────────┐        ┌──────────────────────────────────────────┐
│  frontend/  (Vite SPA)   │  HTTPS │  backend/  (FastAPI)                     │
│  React 18 · TS · Tailwind│ ─────► │  routers → services → repositories → ORM  │
│  TanStack Query · Axios  │  JWT   │  Pydantic v2 · SQLAlchemy 2 · Alembic     │
│  Supabase JS (auth only) │        │  LangGraph · Gemini adapter · PyMuPDF      │
└──────────────────────────┘        └───────────────────┬──────────────────────┘
                                                         │ SQLAlchemy / psycopg3
                                             ┌───────────▼───────────┐
                                             │  PostgreSQL 16        │
                                             │  + pgvector extension │
                                             └───────────────────────┘
```

- The backend **never** trusts a user id, workspace id or role from the client. Identity comes from the verified token; authorisation is re-derived from the database on every request.
- Every failing endpoint returns one stable error envelope: `{"error": {"code","message","details"}}`.
- Every request is tagged with a correlation id (`X-Request-ID`, generated if absent) and one structured log line is emitted.
- The frontend has **one** Axios instance (`src/services/api.ts`) that attaches the JWT and emits a `continuum:unauthorized` event on 401. No permissions or validation live in the frontend.
- Uploaded files are **stored, never executed**.

Full detail: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · endpoints: [docs/API.md](docs/API.md) · contracts: [docs/SCHEMAS.md](docs/SCHEMAS.md) · security: [docs/SECURITY.md](docs/SECURITY.md) · evaluation: [docs/EVALUATION.md](docs/EVALUATION.md) · demo: [docs/DEMO_GUIDE.md](docs/DEMO_GUIDE.md).

---

## 3. Repository layout

```
continuum/
├── backend/                 FastAPI application
│   ├── app/
│   │   ├── api/v1/          routers: health, auth, workspaces, projects, dashboard,
│   │   │                    sources, github, memory, handover, readiness
│   │   ├── core/            settings, security, errors, permissions, dependencies
│   │   ├── db/              engine, session, declarative base
│   │   ├── models/          SQLAlchemy 2 ORM models (incl. models/phase5.py)
│   │   ├── repositories/    data access
│   │   ├── schemas/         Pydantic v2 request/response contracts
│   │   ├── services/        business logic (ingestion, github, memory, review,
│   │   │                    handover, readiness, successor, knowledge, continuity)
│   │   ├── ai/              provider adapter, extractor, verifier, handover writer
│   │   ├── workflow/        LangGraph graph, nodes, state
│   │   ├── evaluation/      ground truth, metrics, runner, synthetic seeder
│   │   └── utils/           files, hashing, text
│   ├── alembic/             migrations (4 revisions, head = phase 5)
│   ├── tests/               pytest suite (real PostgreSQL) — 207 tests
│   ├── alembic.ini
│   └── requirements.txt
├── frontend/                React + Vite SPA
│   └── src/
│       ├── app/             router + providers
│       ├── components/      ui/ (shadcn-style) · common/ · intelligence/ · layout/
│       ├── contexts/        AuthContext
│       ├── hooks/           TanStack Query hooks (incl. use-readiness.ts)
│       ├── lib/             api client, query keys, formatting, phase5 metadata
│       ├── pages/           29 page components (incl. the 6 Phase 5 dashboards)
│       ├── routes/          route guards
│       ├── services/        typed API calls
│       └── types/           shared TS interfaces
├── docker/init/             Postgres init (CREATE EXTENSION vector, uuid-ossp)
├── docs/                    ARCHITECTURE · API · SCHEMAS · SECURITY · EVALUATION · DEMO_GUIDE
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
- Optional: a **GitHub OAuth App** for repository import and a **Gemini API key** for the reconstruction layer

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
| `ALLOW_DEV_AUTH` | backend | local dev | Enable the static dev token. **Must be `false` in production** (the app refuses to start otherwise). |
| `DEV_AUTH_TOKEN` | backend | local dev | Must match the frontend's `VITE_DEV_AUTH_TOKEN` |
| `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` | backend | GitHub | OAuth App credentials |
| `GITHUB_TOKEN_ENCRYPTION_KEY` | backend | GitHub | Fernet key: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `GITHUB_OAUTH_REDIRECT_URI` | backend | GitHub | Must match the OAuth App callback |
| `GITHUB_OAUTH_FRONTEND_REDIRECT` | backend | GitHub | Where the browser lands after callback |
| `GEMINI_API_KEY` | backend | reconstruction | Server-side only. Without it the reconstruction endpoints return 503. |
| `GEMINI_MODEL` | backend | – | Model id, pinned via config (not hard-coded in agent code) |
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

To exercise the reconstruction pipeline, set `GEMINI_API_KEY`. Without it the AI endpoints return a clearly-labelled 503 and the app reports the intelligence layer as unconfigured.

---

## 7. Tests

Both suites use synthetic data and talk to real infrastructure — no mocked persistence.

```bash
# Backend — requires the continuum_test database (see §5.1)
cd backend
.\.venv\Scripts\python.exe -m pytest          # or: python -m pytest
# → 207 passed

# Frontend — type-check, unit/component tests, production build
cd frontend
npm run typecheck     # tsc --noEmit
npm test              # vitest run  → 44 passed across 9 files
npm run build         # tsc --noEmit && vite build
```

Backend coverage areas: health/readiness, auth provisioning, workspace isolation, project CRUD + role enforcement, uploads (valid, oversize, wrong type, denied names, ZIP safety), parsers, the secret scanner, the GitHub boundary, dashboard aggregates, the claim/verification contract (including an assertion that an agent **cannot** set `Verified`), prompt-injection resistance, the permissions matrix, Phase 4 review/handover, and the full Phase 5 surface (readiness scoring, successor tasks, knowledge dependencies, missing knowledge, scorecard, evaluation metrics and comparison, successor exercise).

Frontend coverage areas: API error mapping, formatting/source-metadata helpers, shared states, route guards, and the Dashboard / Source Library / Upload / Login pages.

---

## 8. Scope

### Phase 1 — Foundation ✅
Monorepo, UUID-keyed schema with indexes/FKs, Alembic migrations, pgvector provisioned, Supabase Auth with backend JWT verification and server-side role/workspace checks, workspace & project APIs, and the central typed API client with TanStack Query hooks.

### Phase 2 — Source Ingestion ✅
PDF/Markdown/TXT/ZIP upload with the 10-step pipeline, secret scanning and redaction, normalisation, hash-based dedupe, GitHub OAuth + repository/commit/issue/PR/README/file import, and the source library UI.

### Phase 3 — Project Memory ✅
LangGraph reconstruction: claim extraction, evidence spans, verification verdicts, conflict detection and the uncertainty centre. Model access goes through a provider adapter; the model id is configuration, not code.

### Phase 4 — Review, Approval & Handover ✅
The review queue and human decision actions, conflict resolution, versioned handover generation from **approved** claims only, the approval lifecycle, Markdown/PDF export and the append-only audit trail.

### Phase 5 — Readiness, Successor Experience & Evaluation ✅
Deterministic Handover Readiness Engine (catalog-as-data, configurable weights summing to 100%, banded score with visible blockers), successor workspace (sections A–J), successor task checklist (no invented owners/deadlines), knowledge dependency analysis (with reviewer override), missing knowledge detection, continuity scorecard, and a reproducible evaluation framework (synthetic ground truth + metrics A–I + successor exercise) with run-to-run regression comparison.

**Governance rule, enforced in code:** only a human reviewer may set a claim to **`Verified`**. The AI layer may only ever emit `Supported`, `Uncertain` or `Conflict`; `assert_ai_assignable_status()` raises if an automated pipeline attempts anything else. Readiness scoring counts **only approved claims**.

### Known limitations / untested areas

- The reconstruction layer needs a configured `GEMINI_API_KEY`; without it those endpoints correctly return 503 rather than fabricating results.
- The `vector` extension is provisioned but no embedding columns are defined yet.
- GitHub import is limited to the REST API; `include_changed_files` costs an extra request per record and is off by default.
- Supabase sign-up email confirmation flow is configured on the Supabase side, not in this repository.
- The production Vite bundle exceeds 500 kB in one chunk (a warning, not an error).
- The successor readiness exercise is a **limited** evidence-based check, not a simulation of human competence.
- Security review findings and residual gaps are listed in [docs/SECURITY.md](docs/SECURITY.md).

---

## 9. Deployment notes

- **Frontend → Vercel.** Set `VITE_API_BASE_URL`, and the Supabase/`VITE_DEV_AUTH_TOKEN` variables as needed. Server secrets must **not** be set here.
- **Backend → Render (or equivalent).** Set `DATABASE_URL`, `CORS_ORIGINS` (include the Vercel origin), `ENVIRONMENT=production`, and the Supabase/GitHub/Gemini variables. Run `alembic upgrade head` as a release step. `ALLOW_DEV_AUTH` must be `false` (the app refuses to boot otherwise).
- **Database → Supabase Postgres or a managed PostgreSQL with the `vector` extension.** Run `alembic upgrade head` and ensure `CREATE EXTENSION vector` is permitted.
- Health checks: `/health` (liveness) and `/health/ready` (verifies the database; 503 when degraded).
- All credentials are supplied via environment variables. Nothing is hard-coded and no secret is ever committed.

---

## 10. Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — system design, data model, the readiness engine and evaluation subsystem.
- [docs/API.md](docs/API.md) — every endpoint, roles and error codes.
- [docs/SCHEMAS.md](docs/SCHEMAS.md) — entities and the Claim/Verification contracts.
- [docs/SECURITY.md](docs/SECURITY.md) — threat model, controls, tested scenarios and residual gaps.
- [docs/EVALUATION.md](docs/EVALUATION.md) — ground truth, metric definitions A–I, and the successor exercise.
- [docs/DEMO_GUIDE.md](docs/DEMO_GUIDE.md) — a judge-facing walkthrough of the whole workflow.
