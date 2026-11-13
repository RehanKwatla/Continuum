<div align="center">

<img src="assets/banner.svg" alt="Continuum — Agentic Project Continuity Platform" width="100%"/>

<br/>

**Reconstruct project knowledge from authorised sources, so a handover survives the people who leave.**

<br/>

![CodeZen India 2026](https://img.shields.io/badge/CodeZen_India_2026-Team_Cipher-ff4fa3?style=for-the-badge&labelColor=170a3a)
![Phases](https://img.shields.io/badge/Phases-1→5_Complete-2ee6c5?style=for-the-badge&labelColor=170a3a)
![Backend Tests](https://img.shields.io/badge/Backend_Tests-207_passing-ffb347?style=for-the-badge&labelColor=170a3a)
![Frontend Tests](https://img.shields.io/badge/Frontend_Tests-44_passing-6c8cff?style=for-the-badge&labelColor=170a3a)

![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React_18-20232a?style=flat-square&logo=react&logoColor=61DAFB)
![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?style=flat-square&logo=typescript&logoColor=white)
![Tailwind](https://img.shields.io/badge/Tailwind-06B6D4?style=flat-square&logo=tailwindcss&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL_16-4169E1?style=flat-square&logo=postgresql&logoColor=white)
![pgvector](https://img.shields.io/badge/pgvector-8b5cf6?style=flat-square)
![LangGraph](https://img.shields.io/badge/LangGraph-f472b6?style=flat-square)
![Gemini](https://img.shields.io/badge/Gemini-8E75B2?style=flat-square&logo=googlegemini&logoColor=white)
![Supabase](https://img.shields.io/badge/Supabase-3ECF8E?style=flat-square&logo=supabase&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat-square&logo=docker&logoColor=white)

<img src="assets/divider.svg" width="100%" alt=""/>

**[Judge Access](#-public-judge-access--zero-sign-in-demo) · [Features](#-what-works-today) · [Architecture](#-architecture) · [Quick Start](#-quick-start) · [Tests](#-tests) · [Scope](#-scope--roadmap) · [Deploy](#-deployment) · [Docs](#-documentation)**

</div>

<br/>

## 🏆 Public Judge Access · Zero Sign-In Demo

> [!IMPORTANT]
> Continuum is configured for frictionless evaluation.
> **No sign-in, email, password, Supabase session or GitHub OAuth is needed to explore the product.**
> Open the deployed URL (or local root `/`) and you land directly in the **Public Demo Environment**, pre-loaded with a realistic synthetic workspace.

| | |
| :-- | :-- |
| 🗂️ **Workspace** | `Continuum Demo Workspace` |
| 💳 **Project** | `Payment Gateway System` (ground-truth synthetic architecture) |
| 📄 **Sources** | 8 normalised documentation / ADR sources |
| 🧠 **Memory** | 28 verified / supported project-memory claims with evidence spans and detected conflicts |
| 📦 **Handover** | An approved **v1** handover snapshot |
| 📊 **Readiness** | An active **98.2%** readiness evaluation |

**Safety guards:** public demo endpoints are **read-only by default**, tenant isolation is enforced (non-demo data returns `404`), and a disposable reset is available at `POST /api/v1/public/demo/reset`.

<br/>

## ✨ The Idea

Every project has knowledge that lives only in someone's head, scattered across docs, commits, issues and old decisions. When that person leaves, it leaves with them.

**Continuum reconstructs that knowledge from authorised sources, verifies every claim against evidence, puts humans in charge of what counts as true, and turns the result into a versioned, auditable handover.**

```mermaid
flowchart LR
    A["🔌 CONNECT<br/>sources"] --> B["🧩 RECONSTRUCT<br/>claims"]
    B --> C["🔍 VERIFY<br/>evidence"]
    C --> D["👤 REVIEW<br/>humans decide"]
    D --> E["📦 HANDOVER<br/>versioned"]

    style A fill:#ff4fa3,stroke:#ff4fa3,color:#fff
    style B fill:#ffb347,stroke:#ffb347,color:#1a1a1a
    style C fill:#2ee6c5,stroke:#2ee6c5,color:#1a1a1a
    style D fill:#6c8cff,stroke:#6c8cff,color:#fff
    style E fill:#8b5cf6,stroke:#8b5cf6,color:#fff
```

<div align="center"><img src="assets/divider.svg" width="100%" alt=""/></div>

## 🌈 What Works Today

| Stage | What you get | Status |
| :-- | :-- | :--: |
| 🔌 **CONNECT** | Sign in, create a workspace and project, connect GitHub, upload documents | ✅ |
| 🧩 **RECONSTRUCT** | Normalised source library, claim extraction, evidence verification, conflict detection *(needs a model key, see [Setup](#environment-variables))* | ✅ |
| 🔍 **VERIFY** | Evidence spans, verification verdicts, uncertainty centre | ✅ |
| 👤 **REVIEW** | Review queue, approve / reject / clarify / edit, conflict resolution | ✅ |
| 📦 **HANDOVER** | Versioned handover, approval workflow, Markdown / PDF export, audit trail | ✅ |
| 🎯 **READINESS & SUCCESSOR** | Deterministic readiness engine, successor workspace, checklist, knowledge risk, missing knowledge, continuity scorecard | ✅ |
| 🧪 **EVALUATION** | Synthetic ground truth, reproducible metrics A–I, run comparison, successor exercise | ✅ |

### Highlights

<table>
<tr>
<td width="50%" valign="top">

#### 🔐 Auth & Tenancy
Supabase sign-in with server-side JWT verification (HS256 secret or project JWKS), protected routes and per-request workspace/project membership checks. A resource you can't see returns **404, never 403**, so tenancy never leaks. A clearly-labelled dev-token flow exists for local testing and is **refused in production**.

#### 📥 Hardened Uploads
PDF (PyMuPDF), Markdown, TXT and ZIP through a **10-step pipeline**: magic-byte sniffing, size limits, a secret scanner that redacts and never logs values, SHA-256 dedupe, and zip-slip / path-traversal / expansion protection.

#### 🐙 GitHub Import
Server-side OAuth with **Fernet-encrypted tokens** never exposed to browser JS. Imports commits, issues, PRs, README and text files as normalised sources via REST, with pagination and rate-limit handling. Missing credentials return a labelled 503, never fabricated data.

</td>
<td width="50%" valign="top">

#### 🧠 Human-Governed AI
A LangGraph workflow extracts claims, verifies each against its cited evidence and detects contradictions. **Only a human reviewer can set a claim to `Verified`.** The AI may only emit `Supported`, `Uncertain` or `Conflict`, enforced by `assert_ai_assignable_status()`. No `GEMINI_API_KEY`? Endpoints return 503. Nothing is faked.

#### 📐 Deterministic Readiness
Requirements are *data*. Completion is derived from **approved** claims, their evidence and open conflicts. The score is a pure function of completions and configurable weights. **An LLM never decides a score.** Every evaluation stores the exact weights, results and claim revisions, so any score can be re-derived and audited.

#### 📊 Live Everything
Every dashboard and scorecard number is a live SQL aggregate. There are **no static or seeded source records** anywhere in the application.

</td>
</tr>
</table>

<div align="center"><img src="assets/divider.svg" width="100%" alt=""/></div>

## 🏛️ Architecture

```mermaid
flowchart LR
    subgraph FE["🎨 frontend/ · Vite SPA"]
        direction TB
        F1["React 18 · TypeScript · Tailwind"]
        F2["TanStack Query · Axios"]
        F3["Supabase JS (auth only)"]
    end

    subgraph BE["⚙️ backend/ · FastAPI"]
        direction TB
        B1["routers → services → repositories → ORM"]
        B2["Pydantic v2 · SQLAlchemy 2 · Alembic"]
        B3["LangGraph · Gemini adapter · PyMuPDF"]
    end

    DB[("🐘 PostgreSQL 16<br/>+ pgvector")]

    FE -- "HTTPS + JWT" --> BE
    BE -- "SQLAlchemy / psycopg3" --> DB

    style FE fill:#1d1346,stroke:#ff4fa3,color:#fff
    style BE fill:#0e2a3a,stroke:#2ee6c5,color:#fff
    style DB fill:#2a1b5c,stroke:#ffb347,color:#fff
```

**Design principles**

- 🛡️ The backend **never** trusts a user id, workspace id or role from the client. Identity comes from the verified token; authorisation is re-derived from the database on every request.
- 📬 Every failing endpoint returns one stable envelope: `{"error": {"code", "message", "details"}}`.
- 🔎 Every request carries a correlation id (`X-Request-ID`, generated if absent) and emits one structured log line.
- 🔌 The frontend has **one** Axios instance (`src/services/api.ts`) that attaches the JWT and emits a `continuum:unauthorized` event on 401. No permissions or validation live in the frontend.
- 📁 Uploaded files are **stored, never executed**.

<details>
<summary><b>📂 Repository layout</b></summary>

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
│   │   ├── services/        ingestion, github, memory, review, handover,
│   │   │                    readiness, successor, knowledge, continuity
│   │   ├── ai/              provider adapter, extractor, verifier, handover writer
│   │   ├── workflow/        LangGraph graph, nodes, state
│   │   ├── evaluation/      ground truth, metrics, runner, synthetic seeder
│   │   └── utils/           files, hashing, text
│   ├── alembic/             migrations (4 revisions, head = phase 5)
│   ├── tests/               pytest suite (real PostgreSQL), 207 tests
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

</details>

<div align="center"><img src="assets/divider.svg" width="100%" alt=""/></div>

## 🚀 Quick Start

### Prerequisites

| Requirement | Notes |
| :-- | :-- |
| **Node.js 18+** and npm | frontend |
| **Python 3.12+** | backend |
| **Docker** | only to run PostgreSQL locally |
| **Supabase** project *or* the dev token flow | see [Local auth](#-local-authentication-testing) |
| *Optional* GitHub OAuth App | repository import |
| *Optional* Gemini API key | reconstruction layer |

### 1 · Database

```bash
# from the repository root
docker compose up -d
```

Starts `pgvector/pgvector:pg16` as container **`continuum-db`** on host port **5433** (so it never collides with a local PostgreSQL on 5432). The init script enables `vector` and `uuid-ossp`; data persists in the `continuum_pgdata` volume.

Create the test database once:

```bash
docker exec continuum-db psql -U continuum -d continuum -c "CREATE DATABASE continuum_test;"
```

### 2 · Environment variables

```bash
cp .env.example .env                    # backend reads .env / ../.env
cp frontend/.env.example frontend/.env  # frontend
```

<a id="environment-variables"></a>

<details>
<summary><b>🔧 Full variable reference</b></summary>

<br/>

| Variable | Scope | Required | Purpose |
| :-- | :-- | :--: | :-- |
| `DATABASE_URL` | backend | ✅ | `postgresql+psycopg://continuum:continuum@localhost:5433/continuum` |
| `CORS_ORIGINS` | backend | ✅ | Comma-separated allowed frontend origins |
| `ENVIRONMENT` | backend | ✅ | `development` \| `staging` \| `production` |
| `SUPABASE_URL` | backend | Supabase mode | Project URL |
| `SUPABASE_JWT_SECRET` | backend | Supabase (HS256) | JWT secret; omit to verify via JWKS (RS256) |
| `SUPABASE_JWT_AUDIENCE` | backend | – | Default `authenticated` |
| `SUPABASE_SERVICE_ROLE_KEY` | backend | – | Server-side only |
| `ALLOW_DEV_AUTH` | backend | local dev | Enables the static dev token. **Must be `false` in production** (app refuses to start otherwise) |
| `DEV_AUTH_TOKEN` | backend | local dev | Must match the frontend's `VITE_DEV_AUTH_TOKEN` |
| `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` | backend | GitHub | OAuth App credentials |
| `GITHUB_TOKEN_ENCRYPTION_KEY` | backend | GitHub | Fernet key (see below) |
| `GITHUB_OAUTH_REDIRECT_URI` | backend | GitHub | Must match the OAuth App callback |
| `GITHUB_OAUTH_FRONTEND_REDIRECT` | backend | GitHub | Where the browser lands after callback |
| `GEMINI_API_KEY` | backend | reconstruction | Server-side only. Without it, reconstruction endpoints return 503 |
| `GEMINI_MODEL` | backend | – | Model id, pinned via config (not hard-coded in agent code) |
| `MAX_UPLOAD_SIZE_BYTES` | backend | – | Default 25 MB |
| `MAX_ZIP_EXPANSION_BYTES` | backend | – | Default 100 MB |
| `UPLOAD_DIR` | backend | – | Default `./storage/uploads` |
| `VITE_API_BASE_URL` | frontend | ✅ | `http://localhost:8000/api/v1` |
| `VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY` | frontend | Supabase mode | Public anon key only, **never** a secret |
| `VITE_DEV_AUTH_TOKEN` | frontend | local dev | Must match `DEV_AUTH_TOKEN` |

Generate the Fernet key with:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

</details>

> [!WARNING]
> `VITE_*` values are shipped to the browser. Never put a server secret behind a `VITE_` prefix.

### 3 · Backend

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

| Endpoint | URL |
| :-- | :-- |
| API | <http://localhost:8000/api/v1> |
| Swagger | <http://localhost:8000/docs> |
| Liveness | <http://localhost:8000/health> |
| Readiness | <http://localhost:8000/health/ready> |

### 4 · Frontend

```bash
cd frontend
npm install
npm run dev
```

App → <http://localhost:5173>

<div align="center"><img src="assets/divider.svg" width="100%" alt=""/></div>

## 🔑 Local Authentication Testing

The backend verifies Supabase JWTs in production. For local end-to-end testing **without** a Supabase project, use the development-only bypass:

**1.** Backend `.env`:
```env
ENVIRONMENT=development
ALLOW_DEV_AUTH=true
DEV_AUTH_TOKEN=dev-local-token
```

**2.** `frontend/.env`:
```env
VITE_DEV_AUTH_TOKEN=dev-local-token
```

**3.** Start both services. `GET /health/ready` reports `"dev_auth_enabled": true`, and the Login page shows a clearly-labelled **"Continue with development session"** button.

> [!CAUTION]
> This path is refused whenever `ENVIRONMENT=production`, regardless of `ALLOW_DEV_AUTH`. It is a local-testing affordance, **not** a substitute for real authentication.

- **Use Supabase instead:** fill in `SUPABASE_URL` + `SUPABASE_ANON_KEY` (frontend) and `SUPABASE_JWT_SECRET` or `SUPABASE_URL` (backend), then sign in normally.
- **Exercise reconstruction:** set `GEMINI_API_KEY`. Without it the AI endpoints return a labelled 503 and the app reports the intelligence layer as unconfigured.

<div align="center"><img src="assets/divider.svg" width="100%" alt=""/></div>

## 🧪 Tests

Both suites use synthetic data and talk to real infrastructure. **No mocked persistence.**

```bash
# Backend (requires the continuum_test database)
cd backend
.\.venv\Scripts\python.exe -m pytest      # or: python -m pytest
# → 207 passed

# Frontend
cd frontend
npm run typecheck     # tsc --noEmit
npm test              # vitest run → 44 passed across 9 files
npm run build         # tsc --noEmit && vite build
```

<table>
<tr>
<td width="50%" valign="top">

**Backend coverage**
- Health / readiness, auth provisioning
- Workspace isolation, project CRUD + role enforcement
- Uploads: valid, oversize, wrong type, denied names, ZIP safety
- Parsers and the secret scanner
- The GitHub boundary and dashboard aggregates
- Claim / verification contract, including an assertion that an agent **cannot** set `Verified`
- Prompt-injection resistance and the permissions matrix
- Phase 4 review / handover
- Full Phase 5 surface: readiness scoring, successor tasks, knowledge dependencies, missing knowledge, scorecard, evaluation metrics and comparison, successor exercise

</td>
<td width="50%" valign="top">

**Frontend coverage**
- API error mapping
- Formatting and source-metadata helpers
- Shared states
- Route guards
- Dashboard, Source Library, Upload and Login pages

</td>
</tr>
</table>

<div align="center"><img src="assets/divider.svg" width="100%" alt=""/></div>

## 🗺️ Scope & Roadmap

```mermaid
timeline
    title Continuum build phases
    Phase 1 : Foundation
    Phase 2 : Source Ingestion
    Phase 3 : Project Memory
    Phase 4 : Review, Approval & Handover
    Phase 5 : Readiness, Successor Experience & Evaluation
```

| Phase | Name | Delivered | |
| :--: | :-- | :-- | :--: |
| **1** | 🏗️ **Foundation** | Monorepo, UUID-keyed schema with indexes/FKs, Alembic migrations, pgvector provisioned, Supabase Auth with backend JWT verification and server-side role/workspace checks, workspace & project APIs, central typed API client with TanStack Query hooks | ✅ |
| **2** | 📥 **Source Ingestion** | PDF/Markdown/TXT/ZIP upload with the 10-step pipeline, secret scanning and redaction, normalisation, hash-based dedupe, GitHub OAuth + repo/commit/issue/PR/README/file import, source library UI | ✅ |
| **3** | 🧠 **Project Memory** | LangGraph reconstruction: claim extraction, evidence spans, verification verdicts, conflict detection, uncertainty centre. Model access via a provider adapter; the model id is configuration, not code | ✅ |
| **4** | ✅ **Review, Approval & Handover** | Review queue and human decision actions, conflict resolution, versioned handover generated from **approved** claims only, approval lifecycle, Markdown/PDF export, append-only audit trail | ✅ |
| **5** | 🎯 **Readiness, Successor & Evaluation** | Deterministic Handover Readiness Engine (catalog-as-data, configurable weights summing to 100%, banded score with visible blockers), successor workspace (sections A–J), successor task checklist (no invented owners/deadlines), knowledge dependency analysis (with reviewer override), missing knowledge detection, continuity scorecard, reproducible evaluation framework (synthetic ground truth + metrics A–I + successor exercise) with run-to-run regression comparison | ✅ |

> [!NOTE]
> **Governance rule, enforced in code:** only a human reviewer may set a claim to **`Verified`**. The AI layer may only emit `Supported`, `Uncertain` or `Conflict`; `assert_ai_assignable_status()` raises if an automated pipeline attempts anything else. Readiness scoring counts **only approved claims**.

### Known limitations

- The reconstruction layer needs a configured `GEMINI_API_KEY`; without it those endpoints correctly return 503 rather than fabricating results.
- The `vector` extension is provisioned, but no embedding columns are defined yet.
- GitHub import is limited to the REST API; `include_changed_files` costs an extra request per record and is off by default.
- Supabase sign-up email confirmation is configured on the Supabase side, not in this repository.
- The production Vite bundle exceeds 500 kB in one chunk (a warning, not an error).
- The successor readiness exercise is a **limited** evidence-based check, not a simulation of human competence.
- Security review findings and residual gaps are listed in [docs/SECURITY.md](docs/SECURITY.md).

<div align="center"><img src="assets/divider.svg" width="100%" alt=""/></div>

## ☁️ Deployment

| Layer | Target | Notes |
| :-- | :-- | :-- |
| 🎨 **Frontend** | **Vercel** | Set `VITE_API_BASE_URL` and the Supabase / `VITE_DEV_AUTH_TOKEN` variables as needed. Server secrets must **not** be set here. |
| ⚙️ **Backend** | **Render** (or equivalent) | Set `DATABASE_URL`, `CORS_ORIGINS` (include the Vercel origin), `ENVIRONMENT=production`, and the Supabase / GitHub / Gemini variables. Run `alembic upgrade head` as a release step. `ALLOW_DEV_AUTH` must be `false`. |
| 🐘 **Database** | **Supabase Postgres** or managed PostgreSQL | Needs the `vector` extension. Run `alembic upgrade head` and ensure `CREATE EXTENSION vector` is permitted. |

- 💓 **Health checks:** `/health` (liveness) and `/health/ready` (verifies the database; returns 503 when degraded).
- 🔒 All credentials are supplied via environment variables. Nothing is hard-coded and no secret is ever committed.

<div align="center"><img src="assets/divider.svg" width="100%" alt=""/></div>

## 📚 Documentation

| Document | What's inside |
| :-- | :-- |
| 🏛️ [ARCHITECTURE](docs/ARCHITECTURE.md) | System design, data model, the readiness engine and evaluation subsystem |
| 🔌 [API](docs/API.md) | Every endpoint, roles and error codes |
| 🧬 [SCHEMAS](docs/SCHEMAS.md) | Entities and the Claim / Verification contracts |
| 🛡️ [SECURITY](docs/SECURITY.md) | Threat model, controls, tested scenarios and residual gaps |
| 🧪 [EVALUATION](docs/EVALUATION.md) | Ground truth, metric definitions A–I, and the successor exercise |
| 🎬 [DEMO_GUIDE](docs/DEMO_GUIDE.md) | A judge-facing walkthrough of the whole workflow |

<br/>

<div align="center">

<img src="assets/divider.svg" width="100%" alt=""/>

### *People may leave. The knowledge shouldn't have to.*

Built with ♥ for **CodeZen India 2026 National Hackathon** · **Team Cipher**

</div>
