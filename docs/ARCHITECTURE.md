# CONTINUUM — Architecture

**Agentic Project Continuity Platform** · CodeZen India 2026 · Team Cipher

> People may leave. The knowledge shouldn't have to.

CONTINUUM reconstructs project knowledge from authorised sources, has each extracted
fact verified against its evidence and approved by a human, produces a versioned
handover, and measures — deterministically — how complete that handover is. This
document describes the architecture that is actually implemented in the repository.
Every statement below is traceable to a source file; the file is linked at the point
of the claim.

---

## 1. Overview and workflow

The product workflow is **CONNECT → RECONSTRUCT → VERIFY → REVIEW → HANDOVER**
(also stated in the API root payload in [`main.py`](../backend/app/main.py) and the
[`README.md`](../README.md)):

| Stage | What happens | Where it lives |
| --- | --- | --- |
| **CONNECT** | Sign in, create a workspace and project, connect GitHub, upload documents | [`api/v1/auth.py`](../backend/app/api/v1/auth.py), [`api/v1/workspaces.py`](../backend/app/api/v1/workspaces.py), [`api/v1/projects.py`](../backend/app/api/v1/projects.py), [`api/v1/sources.py`](../backend/app/api/v1/sources.py), [`api/v1/github.py`](../backend/app/api/v1/github.py) |
| **RECONSTRUCT** | The LangGraph workflow extracts claims from sources, validates and deduplicates them, verifies each claim against the exact spans it cites, detects conflicts and stale information, and persists project memory | [`workflow/graph.py`](../backend/app/workflow/graph.py), [`workflow/nodes.py`](../backend/app/workflow/nodes.py) |
| **VERIFY** | Each claim carries a verdict (`supports` / `none`); a verdict produces `Supported`, never `Verified` | [`ai/verifier.py`](../backend/app/ai/verifier.py), [`workflow/nodes.py`](../backend/app/workflow/nodes.py) |
| **REVIEW** | A human reviewer approves, rejects, edits or requests clarification; only a human may set a claim to `Verified` | [`api/v1/memory.py`](../backend/app/api/v1/memory.py), [`services/claim_state_machine.py`](../backend/app/services/claim_state_machine.py) |
| **HANDOVER** | A versioned handover is generated from approved claims only, submitted, approved, published, exported (Markdown / PDF) and archived | [`api/v1/handover.py`](../backend/app/api/v1/handover.py), [`services/handover_service.py`](../backend/app/services/handover_service.py) |

A sixth capability sits on top: a **deterministic readiness assessment**, a guided
**successor workspace**, **knowledge-risk** analysis and a reproducible
**evaluation** subsystem (all Phase 5, see §7–§9).

**Governance rule (enforced in code).** Only a human reviewer may set a claim to
`Verified`; the AI layer may only ever emit `Supported`, `Uncertain` or `Conflict`
([`services/claim_state_machine.py`](../backend/app/services/claim_state_machine.py),
[`workflow/nodes.py`](../backend/app/workflow/nodes.py)). A model `supports` verdict
maps to `Supported` — never `Verified` ([`nodes.py` `status_from_verification`](../backend/app/workflow/nodes.py)).

---

## 2. Technology stack

### Backend

| Concern | Choice | Evidence |
| --- | --- | --- |
| Language / runtime | Python 3.12+ | [`requirements.txt`](../backend/requirements.txt) |
| Web framework | FastAPI (`>=0.115`), Uvicorn | [`requirements.txt`](../backend/requirements.txt), [`main.py`](../backend/app/main.py) |
| Validation / settings | Pydantic v2, pydantic-settings | [`requirements.txt`](../backend/requirements.txt), [`core/config.py`](../backend/app/core/config.py) |
| ORM / migrations | SQLAlchemy 2, Alembic | [`db/session.py`](../backend/app/db/session.py), [`alembic/versions`](../backend/alembic/versions) |
| Database driver | psycopg 3 (`postgresql+psycopg`) | [`core/config.py`](../backend/app/core/config.py) |
| Database | PostgreSQL 16 + pgvector (`pgvector/pgvector:pg16`) | [`docker-compose.yml`](../docker-compose.yml), [`docker/init/01_extensions.sql`](../docker/init/01_extensions.sql) |
| Agent workflow | LangGraph (`>=0.2.0`) | [`requirements.txt`](../backend/requirements.txt), [`workflow/graph.py`](../backend/app/workflow/graph.py) |
| Model access | Gemini REST adapter over `httpx` (vendor-SDK-free) | [`ai/provider.py`](../backend/app/ai/provider.py) |
| Auth | Supabase JWT (HS256 secret or project JWKS) via PyJWT | [`core/security.py`](../backend/app/core/security.py) |
| File parsing | PyMuPDF | [`requirements.txt`](../backend/requirements.txt), [`services/file_parser.py`](../backend/app/services/file_parser.py) |
| GitHub | PyGithub + REST; OAuth tokens Fernet-encrypted at rest | [`services/github_service.py`](../backend/app/services/github_service.py), [`models/github_connection.py`](../backend/app/models/github_connection.py) |

### Frontend

| Concern | Choice | Evidence |
| --- | --- | --- |
| Framework | React 18 | [`package.json`](../frontend/package.json) |
| Build tool | Vite 5 | [`package.json`](../frontend/package.json), [`vite.config.ts`](../frontend/vite.config.ts) |
| Language | TypeScript 5 | [`package.json`](../frontend/package.json) |
| Styling | Tailwind CSS 3 + shadcn-style primitives (Radix UI) | [`tailwind.config.js`](../frontend/tailwind.config.js), [`components/ui`](../frontend/src/components/ui) |
| Server state | TanStack Query v5 | [`app/providers.tsx`](../frontend/src/app/providers.tsx), [`hooks`](../frontend/src/hooks) |
| HTTP | a single Axios instance | [`services/api.ts`](../frontend/src/services/api.ts) |
| Routing | React Router v6 | [`app/router.tsx`](../frontend/src/app/router.tsx) |
| Auth (client) | Supabase JS (auth only) | [`services/auth.ts`](../frontend/src/services/auth.ts) |
| Tests | Vitest + Testing Library | [`package.json`](../frontend/package.json), [`vite.config.ts`](../frontend/vite.config.ts) |

---

## 3. System diagram

```
┌────────────────────────────────┐          ┌───────────────────────────────────────────────┐
│  frontend/  (Vite SPA)         │  HTTPS   │  backend/  (FastAPI)                           │
│  React 18 · TS · Tailwind      │ ───────► │  routers → services → repositories → ORM models│
│  TanStack Query · Axios        │   JWT    │  Pydantic v2 · SQLAlchemy 2 · Alembic          │
│  Supabase JS (auth only)       │ ◄─────── │  LangGraph · Gemini adapter (httpx)            │
│  BrowserRouter + route guards  │  JSON    │  PyMuPDF · PyGithub · Fernet                   │
└────────────────────────────────┘          └───────────────────────┬───────────────────────┘
                                                                     │ SQLAlchemy / psycopg3
                                                         ┌───────────▼───────────┐
                                                         │  PostgreSQL 16         │
                                                         │  + pgvector extension  │
                                                         │  (provisioned; no      │
                                                         │   vector columns)      │
                                                         └───────────────────────┘
```

- The browser is untrusted: identity comes only from a server-verified token; the
  backend re-derives authorisation from the database on every request
  ([`core/security.py`](../backend/app/core/security.py),
  [`core/dependencies.py`](../backend/app/core/dependencies.py)).
- The frontend talks to the API through one Axios instance
  ([`services/api.ts`](../frontend/src/services/api.ts)); no permissions or
  validation live in the frontend.
- Uploaded files are stored, never executed.

---

## 4. Backend layered architecture

The application is built by a factory, `create_app()`, in
[`main.py`](../backend/app/main.py), which wires middleware, exception handlers and
routers.

### 4.1 Layers

```
api/v1/*.py        HTTP routers — request/response shapes, status codes, dependencies
   │
services/*.py      business logic — one service per concern (memory, handover, readiness, …)
   │
repositories/*.py  data access helpers (projects, sources, workspaces, users, github)
   │
models/*.py        SQLAlchemy 2 ORM models (typed columns: UuidPK, UuidFK, JSONB, sa_enum)
```

Pydantic request/response types live separately in [`schemas/`](../backend/app/schemas)
and never leak ORM objects to the wire. Shared primitives include the error envelope
and pagination ([`schemas/common.py`](../backend/app/schemas/common.py)).

### 4.2 Request lifecycle

1. **Middleware.** `CorrelationIdMiddleware` runs first (added last), then
   `CORSMiddleware`. The middleware takes the inbound `X-Request-ID` or generates a
   UUID, stores it on `request.state.request_id`, and echoes it on the response
   ([`main.py`](../backend/app/main.py)).
2. **Dependency injection.** Routers declare dependencies for the database session
   (`get_db`, request-scoped and closed in a `finally`) and for authorisation
   (`resolve_workspace_access` / `resolve_project_access` plus role factories
   `project_reader` / `project_writer` / `project_admin` / `workspace_member`)
   ([`db/session.py`](../backend/app/db/session.py),
   [`core/dependencies.py`](../backend/app/core/dependencies.py)).
3. **Router → service → repository → ORM.** The router validates input, the service
   applies business rules, the repository issues queries, and the ORM maps rows.
4. **Response.** Serialised through the relevant Pydantic schema.

### 4.3 Error envelope

Every failing endpoint returns one stable shape:

```json
{ "error": { "code": "...", "message": "...", "details": { } } }
```

Implemented by `AppError` and its subclasses (`AuthError`, `ForbiddenError`,
`NotFoundError`, `ConflictError`, `ValidationAppError`, `RateLimitError`,
`UpstreamError`, `NotConfiguredError`) plus handlers registered by
`register_exception_handlers(app)` for `AppError`, Starlette `HTTPException`,
`RequestValidationError` and the catch-all `Exception`
([`core/errors.py`](../backend/app/core/errors.py), [`main.py`](../backend/app/main.py)).
`NotConfiguredError` maps to **HTTP 503** with code `not_configured` — used when a
model provider or integration is not configured.

### 4.4 Correlation-id middleware

`CorrelationIdMiddleware` emits exactly one structured log line per request
(`request_id=… method=… path=… status=… duration_ms=…`) and echoes `X-Request-ID`
to the caller; CORS exposes that header so a UI failure can be traced to the server
log ([`main.py`](../backend/app/main.py)).

---

## 5. Data model

All tables use UUID primary keys (via the `UuidPK` type alias), typed foreign keys
(`UuidFK`), timestamps, and JSONB columns (`JsonObject` / `JsonArray`). Enum columns
are stored as `VARCHAR` (`sa_enum`, `native_enum=False`). See
[`models/types.py`](../backend/app/models/types.py) and
[`models/enums.py`](../backend/app/models/enums.py). Models are aggregated in
[`models/__init__.py`](../backend/app/models/__init__.py).

The schema evolved across four Alembic migrations
([`backend/alembic/versions`](../backend/alembic/versions)):

### Phase 1 — foundation (migration `de0d374b689f`)

`users`, `workspaces`, `workspace_members`, `audit_logs`, `projects`,
`github_connections`, `project_repositories`, `sources`, `evidence`, `claims`.
The migration also creates the `vector` and `uuid-ossp` extensions (pgvector
creation is optional/guarded).

### Phase 2 — source ingestion

Ingestion reuses the Phase 1 tables (`sources`, `evidence`); no new tables. Uploads
are normalised, hashed (SHA-256) and deduplicated.

### Phase 3 — project-memory intelligence (migration `52e47b4633ae`)

Adds `processing_runs`, `conflicts`, `conflict_claims`, `evidence_spans`,
`project_memory`, `claim_history`, `open_questions`, `verifications`,
`handover_documents`, and extra columns on `claims` / `evidence` / `sources`
(freshness, warnings, access label, etc.).

### Phase 4 — review, approval and handover (migration `9f3c2a7b1d45`)

Adds `claim_revisions`, `claim_decisions`, `handovers`, `handover_versions`;
`claims.revision_number`; `conflicts.resolution` / `resolution_metadata`; and
widened claim-status columns.

### Phase 5 — readiness, successor and evaluation (migration `b1a7c4d92e08`, current head)

Adds `readiness_evaluations`, `successor_tasks`, `knowledge_dependencies`,
`knowledge_gaps`, `evaluation_runs` ([`models/phase5.py`](../backend/app/models/phase5.py)).

### Key constraints and indexes

- `readiness_evaluations` — index `ix_readiness_evaluations_project_created`
  (project + created-at ordering).
- `successor_tasks` — unique `(project_id, origin_claim_id)` (idempotent derivation).
- `knowledge_dependencies` — unique `(project_id, dependency_key)`; carries a JSONB
  `override` and a computed `effective_risk_status`.
- `knowledge_gap` — unique `(project_id, gap_key)`.

**pgvector** is provisioned at the database level
([`docker/init/01_extensions.sql`](../docker/init/01_extensions.sql),
[`docker-compose.yml`](../docker-compose.yml)) and the client library is a
dependency ([`requirements.txt`](../backend/requirements.txt)), but **no vector
columns or embeddings are defined anywhere in the models** (verified: no
vector/embedding usages under `backend/app`). The extension is reserved for future
semantic retrieval.

---

## 6. AI reconstruction workflow

### 6.1 Graph

The reconstruction graph is built by `build_reconstruction_graph` with
`GRAPH_NAME = "continuum_project_memory_reconstruction"`
([`workflow/graph.py`](../backend/app/workflow/graph.py)). It is a linear pipeline
with conditional escape edges:

```
access_filter → prepare_source_spans → extract_claims → validate_claims
   → verify_claims → detect_conflicts → detect_stale_information
   → persist_project_memory → create_open_questions → prepare_handover_input
```

Conditional edges short-circuit on insufficient sources, no claims, or verification
failure. Each node is a plain, testable method bound to a DB session and an injected
`LLMProvider` ([`workflow/nodes.py`](../backend/app/workflow/nodes.py)). Node
responsibilities:

| Node | Responsibility |
| --- | --- |
| `access_filter` | Apply the source-level filter (explicit selection + `restricted` label) **before** any content can reach a prompt; restricted sources are only usable by `admin`/`owner` |
| `prepare_source_spans` | Create/collect backend-owned evidence spans and per-source isolation on failure |
| `extract_claims` | Run the Extractor per source; per-source failures are isolated |
| `validate_claims` | Cross-source deduplication (merge evidence, keep one claim) |
| `verify_claims` | Verify each claim against the exact spans it cites |
| `detect_conflicts` | Deterministic, time-aware contradiction detection |
| `detect_stale_information` | Flag sources a newer source has superseded |
| `persist_project_memory` | Write claims, evidence, verifications, conflicts, freshness and memory stats |
| `create_open_questions` | Persist unanswered questions from `open_question` claims |
| `prepare_handover_input` | Collect **approved claims only** as the Handover Writer's fixed input |

State is a typed Pydantic model, `ReconstructionState`, with terminal status
constants (`pending` / `running` / `completed` / `partial` / `failed` /
`insufficient_sources`) ([`workflow/state.py`](../backend/app/workflow/state.py)).
Terminal status is set by a node (not the router) because LangGraph only keeps the
value a node returns.

### 6.2 Provider adapter

Model access is abstracted behind an `LLMProvider` `Protocol`
([`ai/provider.py`](../backend/app/ai/provider.py)). `GeminiProvider` (name
`"gemini"`) calls the Gemini `generateContent` REST endpoint over `httpx` — no
vendor SDK. `get_provider()` raises `NotConfiguredError` (HTTP **503**) when no API
key is configured; the router surfaces that 503 rather than fabricating output
([`api/v1/memory.py`](../backend/app/api/v1/memory.py)). Configuration
(`gemini_api_key`, `gemini_model` = `gemini-2.0-flash`, timeouts and output limits)
lives in [`core/config.py`](../backend/app/core/config.py); the `ai_configured`
property is simply `bool(gemini_api_key)`.

### 6.3 Human-verification governance

- AI verdicts map only to `Supported` / `Uncertain` / `Conflict`
  (`status_from_verification`); a verdict never produces `Verified`.
- The state machine in [`services/claim_state_machine.py`](../backend/app/services/claim_state_machine.py)
  defines the legal transitions; `Conflict → Verified` is not legal, rejected claims
  may only be re-reviewed, and an **edited** claim moves back to `Pending Review`.
  An illegal transition raises a `409` conflict.
- The product label for the database status `Verified` is **"Approved"**
  (`REVIEW_STATUS_LABELS`: `VERIFIED → "Approved"`).
- Only the human review endpoints in [`api/v1/memory.py`](../backend/app/api/v1/memory.py)
  can move a claim to `Verified`.

---

## 7. Deterministic Handover Readiness Engine

The readiness engine is **catalog-as-data**: the requirements, weights and bands
live in a single data module, and the score is a pure arithmetic function of stored
claim state. **The LLM never decides readiness.**

### 7.1 Catalog

[`services/readiness_catalog.py`](../backend/app/services/readiness_catalog.py) holds:

- **6 dimensions** (`ReadinessDimension`): `project_context`, `important_decisions`,
  `technical_dependencies`, `ownership_clarity`, `unfinished_work`,
  `risks_and_operations`.
- **Dimension weights** (must total 100): `15 / 15 / 20 / 15 / 15 / 20`.
- **Criticality weights:** `critical = 3`, `important = 2`, `optional = 1`.
- **Completion values:** `Complete = 1.0`, `Partial = 0.5`, `Uncertain = 0.25`,
  `Missing = 0.0`, `Blocked = 0.0`.
- **Bands** (`default_bands`): `score ≥ 90 → strong`, `≥ 75 → mostly_ready`,
  `≥ 50 → needs_review`, otherwise `not_ready`.
- A tuple of ~24 `RequirementSpec`s, indexed by id and by dimension, plus the
  verbatim `SCORING_FORMULA` string.

### 7.2 Formula

```
dimension_score = 100 * Σ( criticality_weight(req) × completion_value(req) )
                     / Σ( criticality_weight(req) )

overall_score   = Σ( dimension_score × dimension_weight / 100 )
```

`ReadinessService` ([`services/readiness_service.py`](../backend/app/services/readiness_service.py))
builds an evaluation context from approved claims and evidence, applies a generic
evaluator plus a small number of special evaluators (e.g. `owner.unowned_flagged`,
`owner.evidence_backed`), and computes per-dimension and overall scores.
`normalise_weights` rejects a weight set that does not total 100. The result includes
blockers and warnings, and the evaluation persists `formula = SCORING_FORMULA`.

### 7.3 Persistence of exact claim revisions

Each `ReadinessEvaluation` stores `claim_revisions` as
`{claim_id: revision_number}` — the exact revision of every claim the score was
computed from. This makes a score reproducible and auditable against the claim state
that produced it, rather than against whatever the claims later became.

Readiness is exposed per project (`GET`/`POST` readiness, history, and a specific
evaluation) in [`api/v1/readiness.py`](../backend/app/api/v1/readiness.py).

---

## 8. Successor experience

The successor experience is a guided workspace assembled from **approved** claims
only, plus successor tasks, knowledge-dependency analysis and missing-knowledge gaps.

### 8.1 Workspace sections (A–J)

`build_workspace` in
[`services/successor_workspace_service.py`](../backend/app/services/successor_workspace_service.py)
produces ordered sections. Where a section has no approved knowledge it states so
rather than inventing content:

| # | Key | Title |
| --- | --- | --- |
| A | `start_here` | Start Here (readiness line, counts, blockers, narrative) |
| B | `project_overview` | Project Overview |
| C | `key_decisions` | Key Decisions |
| D | `technical_architecture` | Technical Architecture |
| E | `responsibilities` | Responsibilities |
| F | `current_work` | Current Work |
| G | `risks_and_blockers` | Risks and Blockers |
| H | `operational_procedures` | Operational Procedures |
| I | `open_questions` | Open Questions |
| J | `first_actions` | First Actions (successor tasks/checklist) |

Every statement links back to its supporting evidence via the same access-aware
evidence index the handover exporter uses, so restricted source material is never
included.

### 8.2 Successor tasks

`SuccessorService.derive` ([`services/successor_service.py`](../backend/app/services/successor_service.py))
derives tasks from approved claims, linking ownership (an index of approved ownership
claims) and dependencies. Derivation is **idempotent** — enforced by the unique
`(project_id, origin_claim_id)` constraint. Tasks expose priority, status, owner,
completion criteria, origin, supporting claim ids and dependency ids, and can be
created manually or updated. The checklist UI is
[`pages/SuccessorChecklist.tsx`](../frontend/src/pages/SuccessorChecklist.tsx).

### 8.3 Knowledge-dependency analysis and missing-knowledge gaps

`KnowledgeRiskService` ([`services/knowledge_service.py`](../backend/app/services/knowledge_service.py)):

- `analyse_dependencies` builds dependency records and flags **single-author
  concentration** as `High` / `Moderate` / `Low` / `Unknown` risk; an analyst may
  apply an `override` (stored as JSONB, surfaced as `effective_risk_status`).
- `detect_gaps` records **missing knowledge** as `KnowledgeGap` rows (keyed by
  `gap_key`) with criticality, a suggested resolution and a status that can be
  updated.

Both are exposed in [`api/v1/readiness.py`](../backend/app/api/v1/readiness.py)
(`knowledge-dependencies`, `knowledge-gaps`, `scorecard`, `successor-workspace`,
`successor-exercise`).

---

## 9. Continuity scorecard and evaluation subsystem

### 9.1 Scorecard

`ContinuityService.scorecard` ([`services/continuity_service.py`](../backend/app/services/continuity_service.py))
aggregates the continuity signals for a project (readiness, task completion, open
conflicts/gaps, etc.) into a single scorecard payload.

### 9.2 Deterministic successor exercise

`run_successor_exercise` asks a **fixed dataset of 8 questions**
(`EXERCISE_DATASET_VERSION = "successor-exercise-v1"`) and records an outcome of
`Completed` / `Blocked` / `Missing_information`. It is deterministic and does not
call a model.

### 9.3 Evaluation: ground truth kept separate from outputs

The evaluation subsystem answers one question honestly: *given a project whose
correct output is known, how well did the real pipeline do?*

- **Ground truth is declarative and stored separately from the system's outputs**
  ([`evaluation/ground_truth.py`](../backend/app/evaluation/ground_truth.py),
  `GROUND_TRUTH_VERSION = "continuum-ground-truth-v1"`,
  `GROUND_TRUTH_PROJECT_NAME = "Payments Service Handover (ground truth)"`). It
  describes claims, a deliberate contradiction, an ownership change over time (not a
  contradiction), stale information, a restricted source and deliberately missing
  knowledge.
- **Metrics are pure functions** of already-loaded data — they never read the
  database, call a model, or invent a number
  ([`evaluation/metrics.py`](../backend/app/evaluation/metrics.py)). Runs cover
  metric families A–I (claim extraction … readiness agreement) with headline metrics
  and inverted metrics; every ratio is `0.0` with `undefined: True` when its
  denominator is zero.
- **Runs are reproducible and persisted** as an immutable `EvaluationRun`
  ([`evaluation/service.py`](../backend/app/evaluation/service.py),
  [`models/phase5.py`](../backend/app/models/phase5.py)). Repeated runs on unchanged
  data produce identical metrics.
- **Comparison.** `compare` requires the same `kind` and `dataset_version`; a metric
  movement smaller than `REGRESSION_TOLERANCE = 0.0001` is treated as noise, so
  genuine regressions are distinguished from float jitter.

Endpoints: `evaluation/runs` (POST/GET list/get/compare) plus a synthetic-project
seeder under the workspace router
([`api/v1/readiness.py`](../backend/app/api/v1/readiness.py)). Full detail:
[`docs/EVALUATION.md`](./EVALUATION.md).

---

## 10. Frontend architecture

### 10.1 Composition

`main.tsx` renders `App` inside `React.StrictMode`
([`main.tsx`](../frontend/src/main.tsx)). `App` nests providers and the router:
`AppProviders` → `BrowserRouter` → `AppRouter`
([`app/App.tsx`](../frontend/src/app/App.tsx)).

`AppProviders` ([`app/providers.tsx`](../frontend/src/app/providers.tsx)) sets up, in
order, a **single** `QueryClient` (`staleTime: 15s`, `refetchOnWindowFocus: false`,
no retry on 4xx and at most 2 retries on 5xx/network for queries, no retry for
mutations), then `ToastProvider`, then `AuthProvider`.

### 10.2 Routing and guards

Routes are declared flat in [`app/router.tsx`](../frontend/src/app/router.tsx):

- Public: `/` (Landing), `/login` (wrapped in `PublicOnlyRoute`).
- Authenticated: every screen renders inside `ProtectedRoute`, which shows a
  session-loading skeleton, redirects unauthenticated users to `/login`, and wraps
  the app frame (`AppShell`) ([`routes/guards.tsx`](../frontend/src/routes/guards.tsx)).
- Project-scoped screens: `/projects/:projectId` (overview, sources, upload, GitHub,
  memory with nested review/claims/conflicts/uncertainty/timeline, handover,
  readiness, successor-workspace, successor-checklist, knowledge-risk, evaluation,
  system-health, audit).

The client-side guard is a **UX affordance only** — the backend re-checks membership
on every request.

### 10.3 Query layer

All server state goes through TanStack Query hooks in [`hooks/`](../frontend/src/hooks).
Cache keys are centralised in a key factory,
[`lib/query-keys.ts`](../frontend/src/lib/query-keys.ts), so invalidation is
predictable. Hooks gate on auth status (`status === "authenticated" && enabled`) so
nothing fires before a session resolves.

### 10.4 HTTP client and session

There is exactly one Axios instance ([`services/api.ts`](../frontend/src/services/api.ts)):
a request interceptor attaches the bearer token; a response interceptor normalises
every failure into an `ApiClientError` that mirrors the backend envelope
(`code`, `status`, `details`) and emits a `continuum:unauthorized` event on 401. The
token is kept in memory and mirrored to `localStorage`
([`lib/session.ts`](../frontend/src/lib/session.ts)); `AuthContext` listens for the
unauthorized event and signs out ([`contexts/AuthContext.tsx`](../frontend/src/contexts/AuthContext.tsx)).

### 10.5 State / empty / loading / error conventions

Shared components enforce one visual language: `EmptyState` (dashed-border panel with
optional action) and `ErrorState` (role="alert" panel with retry) in
[`components/common/States.tsx`](../frontend/src/components/common/States.tsx); loading
uses skeletons ([`components/ui/skeleton.tsx`](../frontend/src/components/ui/skeleton.tsx)).
Error messages come from `toErrorMessage`, which understands `ApiClientError`.

### 10.6 Design system

Dark is the only shipping theme
([`styles/index.css`](../frontend/src/styles/index.css)). Tokens are HSL CSS variables
consumed by Tailwind ([`tailwind.config.js`](../frontend/tailwind.config.js)):

- **Charcoal** canvas `#1E1E1C` (background), elevated cards, deep sidebar.
- **Sand** `#D8CBB3` (`--sand`, wordmark) for type accents.
- **Electric Blue** `#2F6BFF` (`--primary`, `--ring`) reserved for action/interaction.
- Restrained semantic status hues (`--status-ok`, `--status-warn`,
  `--status-danger`, `--status-info`) distinct from the interaction blue.
- Typography: Inter (sans), Manrope (display, applied to headings), JetBrains Mono
  (mono). Utility classes: `.panel`, `.wordmark`, `.label-eyebrow`, `.hairline-top`,
  `.mono`, `.focus-ring`.

---

## 11. Cross-cutting concerns

### 11.1 Authentication

Every endpoint except the health probes requires a bearer token
([`core/security.py`](../backend/app/core/security.py), [`api/v1/health.py`](../backend/app/api/v1/health.py)).
Two sources are accepted:

- **`supabase`** — server-verified JWT: HS256/384/512 with `SUPABASE_JWT_SECRET`, or
  asymmetric (RS256/ES256/EdDSA) via the project JWKS endpoint. Expired/invalid
  tokens raise `AuthError`.
- **`dev`** — a static `DEV_AUTH_TOKEN`, accepted only when `ALLOW_DEV_AUTH=true` and
  `ENVIRONMENT != production`. The application factory refuses this bypass in
  production (`is_production and allow_dev_auth` raises).

Identity always derives from the verified `sub` claim; the backend never accepts a
client-supplied user/workspace id or role.

### 11.2 Tenancy and RBAC

Role ranks are `viewer < member < admin < owner`
([`core/permissions.py`](../backend/app/core/permissions.py)). Access resolution
returns **404 (not 403) for non-members** so tenancy is never leaked; `403` is
returned only when an authenticated member's role is too low
([`core/dependencies.py`](../backend/app/core/dependencies.py)). Convention: reads
require `VIEWER`, mutations `MEMBER`, destructive/integration actions `ADMIN`.
The permission matrix is exercised by
[`tests/test_permissions_matrix.py`](../backend/tests/test_permissions_matrix.py).

### 11.3 Audit trail

Audit logging is **append-only** and never blocks a request: `record()` writes an
`AuditLog` row and swallows (but logs) failures
([`services/audit_service.py`](../backend/app/services/audit_service.py)). Nothing in
the application updates or deletes an audit row. Project-scoped reads
(`project_audit_trail`) filter by `workspace_id` and a metadata `project_id`, so one
project's history cannot leak another's. Phase 4 review/handover actions are
enumerated in `PHASE4_ACTIONS`.

### 11.4 Logging and monitoring

Logging is configured once at import with a single format
([`main.py`](../backend/app/main.py)). The correlation-id middleware emits exactly one
structured line per request with `request_id`, method, path, status and duration, and
echoes `X-Request-ID` to the caller for end-to-end tracing.

### 11.5 Health checks

[`api/v1/health.py`](../backend/app/api/v1/health.py) exposes:

- `GET /health` — **liveness**, no database access.
- `GET /health/ready` — **readiness**, runs `SELECT 1` and returns **503** when
  degraded. It reports posture only: `supabase_auth_configured`,
  `github_oauth_configured`, `dev_auth_enabled` — never secret values.

---

## 12. Known limitations and untested areas

Stated honestly; each is verifiable in the repository.

- **AI requires a configured key.** The LangGraph workflow and the Gemini adapter
  cannot run without `GEMINI_API_KEY`; unconfigured calls return HTTP **503**
  (`not_configured`) rather than fabricated output
  ([`ai/provider.py`](../backend/app/ai/provider.py), [`api/v1/memory.py`](../backend/app/api/v1/memory.py)).
  There is no offline/echo fallback in the shipping path.
- **pgvector is provisioned but unused.** The `vector` extension and the `pgvector`
  client dependency exist, but no vector column or embedding is defined anywhere
  under `backend/app`; semantic retrieval is not implemented
  ([`docker/init/01_extensions.sql`](../docker/init/01_extensions.sql),
  [`models/`](../backend/app/models)).
- **Vite bundle size.** The production build produces a single large chunk with no
  route-level code splitting (no dynamic imports; no `manualChunks` in
  [`vite.config.ts`](../frontend/vite.config.ts)) and exceeds 500 kB — a Vite
  warning, not an error (recorded in [`README.md`](../README.md) §8).
- **Supabase sign-up email confirmation is external.** The confirmation flow is
  configured on the Supabase side, not in this repository
  ([`README.md`](../README.md) §8). Local development instead uses the
  development-token path, which is refused in production.
- **GitHub import is REST-only and can cost extra requests.** `include_changed_files`
  issues an additional request per record and is off by default
  ([`services/github_service.py`](../backend/app/services/github_service.py),
  [`README.md`](../README.md) §8).
- **Readiness is a completeness measure, not a success proof.** The engine measures
  how complete the approved knowledge is; the `start_here` narrative states
  explicitly that a high score is "not proof that a successor will succeed"
  ([`services/successor_workspace_service.py`](../backend/app/services/successor_workspace_service.py)).
- **Evaluation is scoped to one synthetic dataset.** Metrics are computed against a
  single declarative ground truth (`continuum-ground-truth-v1`); different datasets
  are not comparable unless they share `kind` and `dataset_version`
  ([`evaluation/service.py`](../backend/app/evaluation/service.py)).
- **Documentation drift.** [`README.md`](../README.md) still describes the project as
  "Phase 1 + Phase 2" with Phase 3 "NOT implemented"; the code, migrations and
  routers in fact implement Phases 3–5. This file and
  [`docs/EVALUATION.md`](./EVALUATION.md) reflect the implemented system; the README
  is out of date.

Related documents: [`docs/API.md`](./API.md) (endpoints),
[`docs/SCHEMAS.md`](./SCHEMAS.md) (entities and claim/verification contracts),
[`docs/SECURITY.md`](./SECURITY.md) (controls and threat model),
[`docs/EVALUATION.md`](./EVALUATION.md) (evaluation framework).
