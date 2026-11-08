# CONTINUUM — Judge Demo Guide

**Agentic Project Continuity Platform** · CodeZen India 2026 National Hackathon · Team Cipher

A judge-facing walkthrough: what to show, what to click, what data to expect, and which API
endpoint backs each screen. Follow it top to bottom and the demo runs in ~7 minutes.

---

## 0. Zero-Friction Public Judge Access Mode

> [!IMPORTANT]
> **NO SIGN-IN OR CREDENTIALS REQUIRED FOR JUDGES.**
> For the CodeZen Hackathon, judges can open any deployed URL directly in a private/incognito window without signing in, registering, or providing an email address.
>
> - **Direct landing:** Visiting `/` or `/dashboard` loads the full dashboard and seeds the **Continuum Demo Workspace** and **Payment Gateway System** project automatically.
> - **Unobtrusive environment badge:** The top navigation bar clearly flags `PUBLIC DEMO ENVIRONMENT`.
> - **Pre-seeded synthetic data:** Includes 8 documentation sources (ADRs, architecture, runbooks, OpenAPI spec), 28 claims across Core Architecture, Database, Authentication, API & Integrations, Ops & Runbooks, 1 resolved and 1 open conflict, an approved v1 handover, and a 98.2% readiness evaluation.
> - **Safety guards:** Public demo endpoints are read-only by default (`403 public_demo_read_only`) to prevent state corruption, with strict workspace isolation.
> - **Safe disposable reset:** Judges can click **"Reset Demo Data"** on the dashboard or in the profile menu at any time to re-seed the baseline demonstration workspace.

---

## 1. What this demo proves + prerequisites

### What the demo proves

CONTINUUM turns the scattered evidence a departing engineer leaves behind — documents, commits,
READMEs, issues — into **verified, traceable project memory**, and then measures whether a
successor can actually take over. The demo shows three claims end to end:

1. **Reconstruction is grounded, not invented.** Every claim the system produces links back to a
   source and a piece of evidence. The AI can only ever emit `Supported`, `Uncertain`, or
   `Conflict` — **only a human can set `Verified`**.
2. **Continuity is scored deterministically.** Readiness, the scorecard, gaps, dependencies and
   the successor checklist are computed from database rows — **no LLM in the scoring path** — so
   the same data always produces the same number.
3. **Quality is measurable and reproducible.** A synthetic ground-truth dataset plus a fixed
   successor question set let us report metrics and detect regressions run-over-run.

The product workflow is **CONNECT → RECONSTRUCT → VERIFY → REVIEW → HANDOVER**, wrapped by a
Phase 5 layer: **readiness · successor experience · knowledge risk · evaluation**.

### Design system (if asked about look & feel)

| Token | Value | Use |
| --- | --- | --- |
| Charcoal | `#1E1E1C` | Primary text / dark surfaces |
| Sand | `#D8CBB3` | Neutral surfaces, accents |
| Electric Blue | `#2F6BFF` | Primary action, links, selected state |

### Prerequisites

- **Docker** (for the Postgres + pgvector container).
- **Python 3.11+** and **Node 18+**.
- A shell at the repo root.

Optional — the demo runs fully without these, but set them to show the "configured" states:

| Optional integration | Env vars | What it unlocks |
| --- | --- | --- |
| Supabase Auth | `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_JWT_SECRET` | Real sign-in instead of the dev session |
| Gemini / LLM extraction | `GEMINI_API_KEY` (and model env) | Live claim extraction & handover generation |
| GitHub OAuth | `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET` | Live repository ingestion |

> **Demo tip:** leave the LLM/GitHub keys configured if you have them so the "Connect" and
> "Reconstruct" steps do real work. If not, the deterministic surfaces (Readiness, Scorecard,
> Knowledge risk, Evaluation plumbing, Audit) still all run — just say so (see §5).

---

## 2. Pre-demo checklist

Run these in order. Everything below is copy-pasteable.

| # | Check | Command / action | Expected result |
| --- | --- | --- | --- |
| 1 | Database container up | `docker compose up -d` | Container `continuum-db` running, Postgres exposed on host port **5433** |
| 2 | Migrations applied | `alembic upgrade head` (in `backend/`) | Completes with no pending revisions |
| 3 | Backend running | `uvicorn app.main:app --reload` (in `backend/`) | Listening on **http://localhost:8000** |
| 4 | Backend healthy | open `http://localhost:8000/health/ready` | `status: ok`, `database: ok`, and `dev_auth_enabled: true` |
| 5 | Frontend running | `npm run dev` (in `frontend/`) | Vite dev server on **http://localhost:5173** |
| 6 | Frontend calls an authenticated backend | dev token set | `VITE_DEV_AUTH_TOKEN=dev-local-token` in `frontend/.env` matches backend `DEV_AUTH_TOKEN` |
| 7 | Dev auth enabled on backend | env check | `ENVIRONMENT=development` and `ALLOW_DEV_AUTH=true` |
| 8 | Sign in with a dev session | open `/login` → "Continue with a development session" | Lands on `/dashboard` |
| 9 | Synthetic project seeded | see below | A project named **"Payments Service Handover (ground truth)"** appears |

**Seeding the synthetic project (ground truth):**

- Create/open any workspace, go to `/evaluation`, and in the empty state click
  **"Seed ground-truth corpus"** (admin-only). This is backed by
  `POST /workspaces/{workspaceId}/evaluation/synthetic-project`.
- This creates the **inputs only** — 5 source documents (see Step 6). It deliberately does **not**
  create claims: those must come out of the real reconstruction pipeline, which is exactly what the
  evaluation measures.

> **Sanity check before judges arrive:** open `/system-health`. Everything should be green:
> Database ok, Overall status ok, and no unexpected recent failures.

---

## 3. Scripted walkthrough (14 steps)

Each step lists **what to click**, **what data to expect**, and the **API endpoint** behind it.

### Step 1 — Landing (`/`)

- **Click:** open the app root.
- **Expect:** the marketing page with the workflow strip
  **Connect → Reconstruct → Verify → Review → Handover**.
- **Say:** "This is the journey we're going to walk — five stages, and then a measurement layer on
  top."
- **Endpoint:** none (static).
- **Note:** some on-screen marketing copy still says later stages are "not active in this build" —
  that copy is stale. The stages are implemented; proceed to prove it.

### Step 2 — Sign in (`/login`)

- **Click:** **"Continue with a development session"** (shown when the backend reports
  `dev_auth_enabled`). If Supabase is configured, the sign-in/signup tabs are also available.
- **Expect:** redirect to `/dashboard`. Narrative text on the page: *"People leave. Knowledge stays."*
- **Endpoint:** `POST /auth/session` then `GET /auth/me`.
- **Say:** "Auth is server-side JWT verification — with a dev-session bypass so you can follow along
  without an account."

### Step 3 — Dashboard (`/dashboard`)

- **Click:** land here after login; point at the tiles and the "New project" button.
- **Expect:** metric tiles — **Active projects, Connected sources, Processed records, Pending
  reviews**; ingestion-status breakdowns; recent projects; recent source activity; pending actions.
- **Say:** "One workspace, and every project's continuity state at a glance."
- **Endpoints:** aggregate reads over `GET /projects`, `GET /projects/{id}/sources` and the memory
  counts.

### Step 4 — Create / open the project (`/projects/new`)

- **Click:** **New project** (or open the seeded **"Payments Service Handover (ground truth)"**
  project from the list at `/projects`).
- **Expect:** the create form has **Workspace, Project name, Description, Departing role, Successor
  role, Status**.
- **Say:** "We model *who is leaving* and *who is arriving* — that framing drives everything
  downstream."
- **Endpoint:** `POST /projects` (create), `GET /projects/{id}` (open).

### Step 5 — Project workspace + Sources (Overview, `/projects/:projectId` → Sources, `/projects/:projectId/sources`)

- **Click:** walk the workspace tab bar — **Overview, Sources, Memory, Review queue, Timeline,
  Handover, Readiness, Successor, Checklist, Knowledge risk, Evaluation, System health, Audit**. Open
  **Sources**.
- **Expect:** the Source Library table with status filter chips, search, and source-type / processing
  status selects. Sources show a processing status.
- **Say:** "Everything in CONTINUUM starts as a source with provenance — nothing is asserted without
  a paper trail."
- **Endpoint:** `GET /projects/{id}/sources`.

### Step 6 — Connect: GitHub + Document upload (`/projects/:projectId/sources/github`, `/projects/:projectId/sources/upload`)

- **Click:** open the **GitHub** tab, then the **Upload** tab. If GitHub OAuth is not configured, the
  boundary card explains the remediation steps until it is.
- **Expect (GitHub):** a repository list, import-config toggles (commits, issues, PRs, README, files,
  changed_files, max_items) and an **Import into this project** button. GitHub OAuth is handled
  **server-side** — no token ever touches the browser.
- **Expect (Upload):** a drag-and-drop zone accepting **PDF, Markdown, TXT, ZIP** up to **25 MB**,
  with an 8-step "What happens on upload" list; per-file ingestion results afterwards. Ingestion runs
  a **secret scanner** — secrets are detected and redacted.
- **Say:** "Uploads are scanned for secrets before anything is stored."
- **Endpoints:** `GET /github/status`, `GET /github/boundary`, `GET /github/repositories`,
  `POST /projects/{id}/github/import`, `POST /projects/{id}/sources/upload`.

**Seeded corpus (if using the synthetic project, Step 8):** `architecture-notes.md`,
`commit 9f8c2ab`, `README.md`, `issue #412`, and the restricted `restricted-credentials.md`.
Note the built-in contradiction: `architecture-notes.md` (Feb 2024) says **PostgreSQL 13** while
`commit 9f8c2ab` (Jun 2024) says **PostgreSQL 15** — a **stale README** and a **restricted**
credential document are also present.

### Step 7 — Reconstruct memory (`/projects/:projectId/memory`)

- **Click:** **Reconstruct project memory** (re-run shows as **Re-run reconstruction**).
- **Expect:** metric tiles (Claims, Sources, Open conflicts, Flagged for review), verification-status
  bars, knowledge-by-category, and a **Latest reconstruction run**. Claims are grouped and each is
  pending human review — the AI has assigned a verdict but **not** `Verified`.
- **Say:** "The pipeline produced claims with evidence. Notice none are Verified — that's the
  governance rule: AI proposes, humans approve."
- **Endpoint:** `POST /projects/{id}/memory/reconstruct`, then `GET /projects/{id}/memory`.

### Step 8 — Review queue (`/projects/:projectId/memory/review`)

- **Click:** open **Review queue**; inspect a claim, then approve/reject or request clarification.
- **Expect:** claim cards, each with an **"AI: …"** verdict badge and a **"Human: …"** review badge.
  Filters and an order select are available.
- **Say:** "AI can only ever say Supported, Uncertain, or Conflict. The moment I approve, the claim
  becomes Verified — and *only* a human action can do that."
- **Endpoints:** `GET /projects/{id}/review-queue`; approve / reject / request-clarification / edit /
  verify claim endpoints under `/projects/{id}/claims/…`.
- **Point out the contradiction:** in the seeded project, the Postgres 13 vs 15 claim pair surfaces a
  conflict (Step 9).

### Step 9 — Conflict centre (`/projects/:projectId/memory/conflicts`)

- **Click:** open **Conflicts**; select the open conflict on the left; read the detail on the right.
  Record a decision via the resolution radios + required note (≥4 chars) → **Record decision**, or
  **Dismiss as not a contradiction**.
- **Expect:** filters (Open / Resolved / Dismissed / All findings); a resolution form that requires a
  note. **Admin role required** to resolve.
- **Say:** "When the evidence disagrees — Postgres 13 here, Postgres 15 there — CONTINUUM refuses to
  guess. It surfaces the conflict and makes a human decide, and records why."
- **Endpoints:** `GET /projects/{id}/conflicts`, `GET /projects/{id}/conflicts/{conflict_id}`,
  `POST /projects/{id}/conflicts/{conflict_id}/resolve`.

### Step 10 — Handover (`/projects/:projectId/handover`)

- **Click:** **Generate handover** (later **Regenerate**); then walk the lifecycle buttons
  **Submit → Approve → Publish**; try **Export MD** / **Export PDF**. Switch tabs **Document**,
  **Versions (N)**, and **Successor view** (unlocked once a version is **Published**).
- **Expect:** the handover is assembled only from **Verified** claims; the lifecycle buttons enable/
  disable by state (Submit from Draft; Approve from Draft/In Review; Publish from Approved; Archive
  anytime); exports produce files; **Successor view** appears only after publish.
- **Say:** "The handover document contains only what humans approved. Its lifecycle is explicit:
  draft, in review, approved, published, archived — all versioned and auditable."
- **Endpoints:** `POST /projects/{id}/handovers/generate`, `GET /projects/{id}/handovers`,
  `GET /projects/{id}/handovers/{id}`, `GET /projects/{id}/handovers/{id}/versions`,
  `PATCH /projects/{id}/handovers/{id}`, submit/approve/publish/archive, and
  `…/export.md` / `…/export.pdf`.
- **If the LLM key is missing:** the UI shows an `ai_not_configured` notice instead of an error page.
  Say so plainly (§5).

### Step 11 — Readiness (`/projects/:projectId/readiness`)

- **Click:** **Run evaluation** (later **Re-evaluate**). Read the overall score, the band, the
  blockers, then the dimension grid and the **Project continuity scorecard**.
- **Expect:** overall **score /100** with a band — one of **Strong handover readiness**,
  **Mostly ready, some gaps**, **Needs additional review**, **Not ready** — plus critical blockers,
  warnings, per-dimension scores, a requirements+evidence table, and the scorecard's five counts:
  **Pending review items, Unresolved conflicts, Open knowledge gaps, High-risk dependencies, Successor
  tasks remaining**. Evaluation history is listed below.
- **Say:** "This number is deterministic — no LLM. It's a weighted read over six dimensions:
  project context (15), important decisions (15), technical dependencies (20), ownership clarity
  (15), unfinished work (15), risks & operations (20). Only Verified claims count."
- **Endpoint:** `POST /projects/{id}/readiness/evaluate`, then `GET /projects/{id}/readiness`,
  `GET /projects/{id}/readiness/history`. **Member role required** to evaluate.

### Step 12 — Successor experience (`/projects/:projectId/successor-workspace` + `/successor-checklist`)

- **Click:** open **Successor**; scroll the A–J section nav (e.g. "A · Start here", each letter
  generated from the section index). Read the "Known missing knowledge" card. Then open **Checklist**.
- **Expect (Successor):** a counts bar — approved claims, awaiting review, open conflicts, open gaps,
  tasks remaining, published handover version — and per-section cards; the first section, **Start
  here**, shows readiness tiles, an orientation narrative, and blockers. Claims link through to
  `/memory/claims/{id}`.
- **Expect (Checklist):** status counters (Not Started / In Progress / Blocked / Completed); a task
  list with **priority**, **status**, **origin** (a ✨/"suggested" origin is AI-derived), a
  **"Blocked by prerequisites"** badge where applicable, owner, completion criteria, and supporting
  claim chips. Task status is editable via a Select.
- **Click:** **Derive from knowledge** to auto-suggest tasks from the approved memory; **Add task** to
  add one manually.
- **Say:** "The successor doesn't get a wall of text — they get a guided workspace and a checklist
  derived from the approved knowledge, with blockers made explicit."
- **Endpoints:** `GET /projects/{id}/successor-workspace`; `GET/POST /projects/{id}/successor-tasks`,
  `POST /projects/{id}/successor-tasks/derive`, `GET/PATCH /projects/{id}/successor-tasks/{task_id}`.

### Step 13 — Knowledge risk (`/projects/:projectId/knowledge-risk`)

- **Click:** **Detect gaps** and **Analyse dependencies**. Open the **Dependencies (N)** and
  **Missing knowledge (N)** tabs.
- **Expect (Dependencies):** cards with a **risk badge**, the involved people, an evidence summary,
  and — where a human overrode the model — a **"Reviewer override"** badge and form (**admin** role
  required to override).
- **Expect (Missing knowledge):** gap cards with a status select (**Open / In Progress / Resolved /
  Accepted Risk**). A human can record a risk as deliberately **Accepted Risk**.
- **Say:** "Continuity risk is two things: knowledge that lives in too few heads, and knowledge that
  is simply missing. Both are surfaced, and a reviewer can override the model's judgement."
- **Endpoints:** `GET /projects/{id}/knowledge-dependencies`, `POST …/analyse`,
  `GET …/{dependency_id}`, `POST …/{dependency_id}/override`; `GET /projects/{id}/knowledge-gaps`,
  `POST …/detect`, `GET/PATCH …/{gap_id}`.

### Step 14 — Evaluation, System health, Audit (`/evaluation`, `/system-health`, `/audit`)

- **Click (Evaluation):** open **Evaluation**; review the three tabs — **Extraction metrics**,
  **Successor exercise**, **Runs and regressions**. Run **Seed ground-truth corpus** (admin, empty
  state), **Run evaluation** (admin), and **Run successor exercise** (member). Use the base/candidate
  selects for a **comparison**.
- **Expect:** metric tiles labelled `A_claim_extraction … I_readiness_agreement`
  (`G_unsupported_handover_rate` is inverted — lower is better), a `permission_leakage_passed` badge,
  and a successor-exercise report showing **Attempted / Completed / Blocked / Missing information /
  Exercise score**. The exercise answers a fixed 8-question set (identify deployment blocker, locate
  rollback procedure, identify owner, describe current status, find open question, plus repository,
  external service, retry policy) with dataset version `successor-exercise-v1`. Repeated runs on
  unchanged data are identical.
- **Click (System health):** show the API service card, the Database-and-integrations card
  (Readiness, Database, Supabase auth, GitHub OAuth, Dev auth), the tiles, and the breakdowns. It
  auto-refreshes every 30s.
- **Click (Audit):** open **Audit**; filter by **All activity / Approvals / Rejections / Claim edits /
  Clarifications / Conflict decisions / Handover / Exports**. Each action (e.g. `claim_approved`,
  `conflict_resolved`, `handover_published`, `handover_exported`) is timelined.
- **Say:** "Finally, we measure ourselves. A ground-truth dataset with a known contradiction, a
  fixed successor quiz, regression comparison between runs, a live health view, and a full audit
  trail. We can prove the system works — and prove when a change breaks it."
- **Endpoints:** `POST /workspaces/{workspaceId}/evaluation/synthetic-project`; `POST/GET
  /projects/{id}/successor-exercise`; `POST/GET /projects/{id}/evaluation/runs`,
  `GET …/compare`, `GET …/runs/{run_id}`; `GET /projects/{id}/system-health`;
  `GET /projects/{id}/audit`.

---

## 4. The 20-second pitch

> **People leave. Knowledge stays.**
>
> When an engineer quits, their context leaves with them — in half-written docs, stale READMEs, and
> Slack threads nobody reads. **CONTINUUM** ingests everything they left behind — documents, commits,
> issues — and reconstructs **verified, traceable project memory**. The AI proposes; **only humans
> approve**. It then scores handover readiness deterministically, flags the knowledge that is missing
> or lives in too few heads, and hands the successor a guided workspace and checklist instead of a
> wall of text. And because we hold ourselves to evidence, we ship a **ground-truth evaluation
> framework** that measures the handover and catches regressions. **Connect, reconstruct, verify,
> review, hand over — and prove it worked.**

---

## 5. Honesty and limits — say these out loud

Judges reward candour. Volunteer these:

- **The AI does not decide truth.** Extraction can only emit `Supported`, `Uncertain`, or `Conflict`.
  `Verified` is a human-only state. If a judge asks "what stops the AI hallucinating?", this is the
  answer.
- **Scoring is deterministic, not AI.** Readiness, the scorecard, gaps, dependencies, and the
  checklist are computed from database rows — same data, same number. The LLM is in *extraction* and
  *handover drafting*, not in scoring.
- **A couple of UI copy strings are stale.** Some landing/login/marketing text predates Phase 3–5 and
  still says later stages are "not active" or shows an old phase label. The functionality is present
  — we can read the copy as a known cosmetic backlog item.
- **The successor exercise is a limited check, not a person.** It answers a **fixed, project-specific
  question set** from approved knowledge and reports what the handover can and cannot answer. It does
  **not** simulate human competence.
- **Ingestion is bounded and safe.** GitHub OAuth is server-side (tokens never reach the browser);
  uploads are capped at 25 MB and scanned for secrets, with a **restricted access label** honoured in
  the seeded dataset.
- **Optional integrations may be off in this environment.** Without the LLM key, "Generate handover"
  shows an `ai_not_configured` notice; without GitHub keys, the GitHub screen shows a boundary card
  with remediation steps. The deterministic surfaces run regardless — say which is on before you
  click.
- **Evaluation runs on a synthetic project by design.** The ground-truth corpus is synthetic so the
  expected answer is known; that is what makes the metrics reproducible.

---

## 6. FAQ — likely judge questions

| Question | Answer |
| --- | --- |
| **Does the AI decide whether a claim is true?** | No. AI can only emit `Supported` / `Uncertain` / `Conflict`. Only a human sets `Verified`. Approved (Verified) claims are the only ones that reach scoring and the handover. |
| **Is the readiness score just an LLM guess?** | No. It's a deterministic weighted read over six dimensions (project context 15, decisions 15, technical dependencies 20, ownership 15, unfinished work 15, risks/ops 20), with bands at 90/75/50 and a published formula and requirements catalog. |
| **How do you prevent hallucinated claims?** | Every claim carries evidence and links to its source. Stale sources, restricted sources, and contradictions are modelled explicitly, and the reconstruction surfaces conflicts (e.g. Postgres 13 vs 15) rather than silently choosing. |
| **What happens when evidence conflicts?** | The Conflict Centre surfaces it. A human resolves it with a required written rationale, or dismisses it as not a contradiction. Admin-gated, fully audited. |
| **Can we trust the demo data?** | Yes — the synthetic ground-truth project is generated by the same code path the product uses. It pins a known contradiction (PostgreSQL 13 vs 15), a stale README, and a restricted document, so the metrics are reproducible. |
| **How do you know it actually helps?** | The Evaluation dashboard runs extraction metrics (`A_claim_extraction … I_readiness_agreement`), a fixed successor exercise (8 questions, dataset `successor-exercise-v1`), and run-over-run regression comparison. `permission_leakage_passed` guards against leaking restricted knowledge. |
| **Is anything here made up?** | The scoring is deterministic and the evaluation is reproducible — both by design. We're explicit about what the successor exercise is (a fixed question set, not a human simulation) and about which optional integrations are live in this environment. |
| **Tests?** | 207 backend tests and 44 frontend tests. |
| **What's the stack?** | Backend: FastAPI + PostgreSQL + `pgvector`, Supabase Auth (server-side JWT verification), GitHub OAuth server-side ingestion. Frontend: React 18 + Vite + TypeScript + TailwindCSS + TanStack Query + Axios. |
| **How do I run it?** | `docker compose up -d` (Postgres on 5433) → `alembic upgrade head` → backend `uvicorn app.main:app` on 8000 → frontend `npm run dev` on 5173. Confirm `/health/ready` shows `dev_auth_enabled: true`, then sign in with the development session. |
