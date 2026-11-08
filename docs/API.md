# Continuum — API Reference

**Agentic Project Continuity Platform** · Phase 1 (Foundation) + Phase 2 (Source Ingestion)

> "People may leave. The knowledge shouldn't have to."

Base URL (local development): `http://localhost:8000/api/v1`
Interactive schema: `/docs` (Swagger UI) · `/redoc` (ReDoc) · `/openapi.json`

---

## 1. Conventions

### Authentication

Every endpoint except the health probes requires a bearer token:

```
Authorization: Bearer <token>
```

Two token sources are accepted:

| Provider | When | Notes |
| --- | --- | --- |
| `supabase` | Always, when the backend has Supabase credentials | A Supabase-issued access token, verified server-side (HS256 secret **or** the project JWKS endpoint for RS256/ES256/EdDSA). |
| `dev` | **Development only** | A static `DEV_AUTH_TOKEN`, accepted only when `ALLOW_DEV_AUTH=true` **and** `ENVIRONMENT != production`. The backend refuses this bypass in production. |

The backend **never** accepts a user id, workspace id or role supplied by the client. Identity always comes from the verified token `sub` claim; authorisation is re-derived from the database on every request.

### Error envelope

Every failure returns one stable shape:

```json
{
  "error": {
    "code": "forbidden",
    "message": "This action requires the 'member' role or higher in this workspace.",
    "details": { "your_role": "viewer", "required_role": "member" }
  }
}
```

| HTTP | `code` | Meaning |
| --- | --- | --- |
| 400 | `bad_request` | Generic rejection. |
| 401 | `unauthorized`, `invalid_token`, `token_expired` | Missing/invalid/expired credentials. |
| 403 | `forbidden` | Authenticated but the role is too low. |
| 404 | `not_found` | Resource missing **or** not visible to the caller (isolation: non-members see 404, never 403). |
| 405 | `method_not_allowed` | Wrong HTTP verb. |
| 409 | `conflict` | Unique-constraint clash. |
| 422 | `validation_error` | Pydantic/request validation failure; `details.issues` lists each field error. |
| 429 | `rate_limited` | GitHub rate limit reached. |
| 502 | `upstream_error` | GitHub API failure. |
| 503 | `not_configured` | Integration (Supabase/GitHub) is not configured on this server. |
| 500 | `internal_error` | Unexpected server fault (no internals leaked). |

### Roles

Workspace roles, weakest to strongest: `viewer` < `member` < `admin` < `owner`. Endpoints state the **minimum** required role; `owner` always satisfies it.

### Pagination

List endpoints use `?page=1&page_size=20` (or `25` for sources) and return:

```json
{
  "items": [ ... ],
  "meta": {
    "page": 1, "page_size": 20, "total": 42,
    "total_pages": 3, "has_next": true, "has_previous": false
  }
}
```

---

## 2. Health

### `GET /health`  *(also `GET /api/v1/health`)*
Liveness probe. Does **not** touch the database.

```json
{ "status": "ok", "service": "Continuum API", "version": "0.2.0", "environment": "development" }
```

### `GET /health/ready`  *(also `GET /api/v1/health/ready`)*
Readiness probe. Executes `SELECT 1`. Returns **503** with `"status": "degraded"` when the database is unreachable. `dev_auth_enabled` tells the frontend whether the development sign-in path is available.

```json
{
  "status": "ok",
  "version": "0.2.0",
  "database": "ok",
  "supabase_auth_configured": false,
  "github_oauth_configured": false,
  "dev_auth_enabled": true
}
```

Both probes are mounted at the service root **and** under `/api/v1`.

---

## 3. Auth

### `GET /auth/me`
Returns the caller. On first sight the matching local `User` row is provisioned from the verified token (idempotent). Requires: any authenticated principal.

```json
{
  "user": { "id": "uuid", "email": "dev.user@example.com", "full_name": "Development User", "created_at": "2026-01-01T00:00:00Z" },
  "auth_provider": "dev",
  "is_dev_session": true
}
```

### `POST /auth/session`
Idempotent counterpart of `GET /auth/me`, called by the frontend immediately after a Supabase sign-in. Same response shape. Requires: any authenticated principal.

---

## 4. Workspaces

Requires: authenticated user.

### `POST /workspaces` → **201**
Creates a workspace; the caller becomes its `owner` (a membership row is created in the same transaction).

Request:
```json
{ "name": "Platform Handover" }
```
`name`: 1–200 chars.

Response — `WorkspaceRead`:
```json
{
  "id": "uuid",
  "name": "Platform Handover",
  "owner_id": "uuid",
  "created_at": "...",
  "role": "owner",
  "project_count": 0,
  "member_count": 1,
  "members": [
    { "id": "uuid", "user_id": "uuid", "role": "owner", "created_at": "...", "email": "...", "full_name": "..." }
  ]
}
```

### `GET /workspaces`
Lists only the workspaces the caller is a member of. Returns `WorkspaceSummary[]` (no `members` array).

### `GET /workspaces/{workspace_id}`
Minimum role: `viewer`. Returns `WorkspaceRead`. A workspace the caller is not a member of returns **404** (existence is not leaked).

---

## 5. Projects

### `POST /projects` → **201**
Minimum role in the **target** workspace: `member` (authorised before anything is written).

Request:
```json
{
  "workspace_id": "uuid",
  "name": "Payments Handover",
  "description": "Knowledge transfer for the payments service.",
  "departing_role": "Staff Engineer",
  "successor_role": "Senior Engineer",
  "status": "active"
}
```
`status` ∈ `draft | active | handover_in_progress | handed_over | archived` (default `active`).

Response — `ProjectRead` (see §5.3).

### `GET /projects`
Lists projects the caller can access across all their workspaces.

Query parameters:

| Name | Type | Default | Notes |
| --- | --- | --- | --- |
| `workspace_id` | uuid | – | Filter; the workspace is access-checked first. |
| `search` | string | – | Case-insensitive name/description match, max 200. |
| `status` | enum | – | One of the project statuses. |
| `page` | int ≥ 1 | 1 | |
| `page_size` | int 1–100 | 20 | |

Response: `Page<ProjectSummary>`.

### `GET /projects/{project_id}`
Minimum role: `viewer`.

```json
{
  "id": "uuid",
  "workspace_id": "uuid",
  "name": "Payments Handover",
  "description": "...",
  "status": "active",
  "departing_role": "Staff Engineer",
  "successor_role": "Senior Engineer",
  "created_at": "...",
  "updated_at": "...",
  "source_count": 12,
  "repository_count": 1,
  "workspace": { "id": "uuid", "name": "...", "owner_id": "uuid", "created_at": "...", "role": "owner", "project_count": 3, "member_count": 2 },
  "repositories": [
    { "id": "uuid", "provider": "github", "full_name": "acme/payments", "external_id": "123", "description": "...", "default_branch": "main", "is_private": true, "html_url": "...", "connected_at": "...", "metadata": {} }
  ],
  "source_type_counts": { "github_commit": 40, "uploaded_markdown": 3 },
  "processing_status_counts": { "completed": 43 }
}
```

### `PATCH /projects/{project_id}`
Minimum role: `member`. Body accepts any subset of `name`, `description`, `departing_role`, `successor_role`, `status`. Returns the updated `ProjectRead`.

### `DELETE /projects/{project_id}` → **204**
Minimum role: `admin`. Cascades to the project's sources, repositories and claims. Writes an audit entry.

---

## 6. Dashboard

### `GET /dashboard`
Requires: authenticated user. Aggregates computed live from PostgreSQL — **never mocked or seeded**.

```json
{
  "total_projects": 3,
  "total_sources": 128,
  "total_workspaces": 2,
  "total_connected_repositories": 1,
  "source_type_counts": { "github_commit": 90, "uploaded_pdf": 8 },
  "processing_status_counts": { "completed": 126, "duplicate": 2 },
  "recent_projects": [ /* ProjectSummary[] */ ],
  "recent_sources": [
    { "id": "uuid", "project_id": "uuid", "project_name": "Payments Handover", "source_type": "github_commit", "source_name": "abc123 — Fix retry", "processing_status": "completed", "created_at": "..." }
  ],
  "upcoming": ["Claim extraction (Phase 3)", "Evidence verification (Phase 3)", "Handover generation (Phase 3)"]
}
```

`upcoming` is an explicit acknowledgement that Phase 3 is **not** implemented.

---

## 7. Sources (upload & ingestion)

### `POST /projects/{project_id}/sources/upload` → **201**
Minimum role: `member`. `multipart/form-data` with one or more `files` parts.

**Accepted extensions:** `.pdf`, `.md`, `.markdown`, `.txt`, `.zip`
(extensions inside a ZIP: `.pdf`, `.md`, `.markdown`, `.txt`, `.rst`, `.adoc`, `.csv`, `.json`, `.yaml`, `.yml`)

**10-step pipeline** (per file):
1. Sanitise the filename; reject sensitive names (`.env`, `id_rsa`, `credentials.json`, …).
2. Extension allow-list check.
3. Size check against `MAX_UPLOAD_SIZE_BYTES`.
4. Content-type detection by **magic bytes**, cross-checked against the declared extension (`.md`/`.txt` are treated as interchangeable text).
5. Secret scan — detected secrets are redacted (`[REDACTED:<kind>]`) and a value-free warning recorded. Secret **values are never logged or returned.**
6. Parse (PyMuPDF for PDF, structured parsers for Markdown/text) with a character cap.
7. Build normalised metadata (page/segment counts, character count, security-scan summary).
8. Compute a SHA-256 content hash.
9. Duplicate detection on `(project_id, content_hash)` → status `duplicate` with `duplicate_of`.
10. Persist the `Source` (status `completed`) and return the per-file result.

**ZIP safety:** zip-slip/path-traversal and absolute-path rejection; `max_zip_entries` (200) and `max_zip_entry_bytes` (10 MB) limits; total expansion cap (`MAX_ZIP_EXPANSION_BYTES`, default 100 MB); suspicious compression-ratio guard (1000×); nested archives are **skipped** (depth limit 1); denied path parts (`.git`, `node_modules`, `dist`, `.venv`, …) and denied extensions are skipped. Uploaded bytes are **stored, never executed**.

Request:
```
POST /api/v1/projects/{project_id}/sources/upload
Content-Type: multipart/form-data
files=@handover.md;type=text/markdown
files=@design.pdf;type=application/pdf
```

Response — `UploadResponse`:
```json
{
  "results": [
    { "filename": "handover.md", "source_id": "uuid", "source_type": "uploaded_markdown", "status": "completed", "message": "Ingested successfully.", "warnings": [], "duplicate_of": null },
    { "filename": ".env", "source_id": null, "source_type": null, "status": "failed", "message": "This file name is on the sensitive-file deny list and was not ingested.", "warnings": [], "duplicate_of": null }
  ],
  "accepted": 1,
  "duplicates": 0,
  "failed": 1
}
```

`status` ∈ `completed | failed | skipped | duplicate`. Per-file failures do **not** fail the request.

### `GET /projects/{project_id}/sources`
Minimum role: `viewer`.

| Query | Type | Default |
| --- | --- | --- |
| `source_type` | enum | – |
| `processing_status` | enum | – |
| `search` | string (≤300) | – |
| `page` | int ≥ 1 | 1 |
| `page_size` | int 1–100 | 25 |

Response — `SourceListResponse`:
```json
{
  "items": [
    {
      "id": "uuid", "project_id": "uuid",
      "source_type": "uploaded_markdown", "source_name": "handover.md",
      "external_id": null, "author": null, "created_at_source": null,
      "access_label": "workspace", "processing_status": "completed",
      "content_hash": "sha256…", "mime_type": "text/markdown", "size_bytes": 4210,
      "source_url": null, "error_message": null, "warnings": [],
      "created_at": "...", "metadata": { "character_count": 4210, "security_scan": { "has_secrets": false, "secret_types": [], "secret_count": 0 } },
      "content_preview": "First ~400 characters of the normalised content…"
    }
  ],
  "meta": { "page": 1, "page_size": 25, "total": 1, "total_pages": 1, "has_next": false, "has_previous": false },
  "type_counts": { "uploaded_markdown": 1 },
  "status_counts": { "completed": 1 }
}
```

`source_type` values: `github_commit`, `github_issue`, `github_pull_request`, `github_readme`, `github_file`, `uploaded_pdf`, `uploaded_markdown`, `uploaded_text`, `uploaded_zip_entry`.
`processing_status` values: `pending`, `processing`, `completed`, `failed`, `skipped`, `duplicate`.
`access_label` values: `workspace`, `private`, `public`, `restricted`.

### `GET /sources/{source_id}`
Minimum role: `viewer` on the owning project. Returns `SourceRead` — identical to `SourceSummary` plus the full `content` field.

### `DELETE /sources/{source_id}`
Minimum role: `member` on the owning project. Deletes the row, best-effort removes the archived upload from disk (path-checked against the upload root), and writes an audit entry.

```json
{ "id": "uuid", "deleted": true }
```

---

## 8. GitHub

All GitHub OAuth tokens are exchanged and stored **server-side only**, Fernet-encrypted at rest, and are **never returned to the browser**. The OAuth `state` parameter is a short-lived signed JWT bound to the local user id (CSRF protection without a server session). Only the REST API is used — no repositories are cloned.

When the integration is not configured, the endpoints return a **clearly labelled boundary** (503 `not_configured` with remediation steps) rather than fabricated data.

### `GET /github/status`
```json
{ "configured": true, "connected": true, "login": "rehan", "avatar_url": "...", "github_user_id": "123", "scopes": ["repo","read:user"], "connected_at": "...", "message": null }
```

### `GET /github/boundary`
Explicit integration boundary. When unconfigured:
```json
{ "configured": false, "reason": "GitHub OAuth credentials are absent; repository import is inert.", "remediation": ["Set GITHUB_CLIENT_ID …", "…"] }
```

### `POST /github/connect`
Returns the authorisation URL to open in the browser plus the signed `state`.
```json
{ "authorize_url": "https://github.com/login/oauth/authorize?...", "state": "<signed-jwt>" }
```

### `GET /github/callback`
Browser-facing OAuth redirect target (not called by the SPA via XHR). Always redirects to `GITHUB_OAUTH_FRONTEND_REDIRECT`:
`?github=connected` on success, or `?github=error&reason=<code>` (e.g. `missing_parameters`, `rate_limited`).

### `POST /github/disconnect` → **204**
Removes the stored connection and erases the encrypted token.

### `GET /github/repositories`
Lists repositories the caller's token is authorised to read. `limit` 1–300 (default 100). Pagination and rate-limit handling are applied server-side.
```json
{
  "items": [ { "id": "1", "full_name": "acme/payments", "name": "payments", "owner": "acme", "private": true, "description": "...", "default_branch": "main", "html_url": "...", "language": "TypeScript", "stars": 12, "updated_at": "..." } ],
  "total": 1,
  "truncated": false
}
```

### `GET /github/repository?full_name=owner/name`
Metadata for the selection screen. `full_name` 3–300 chars.
```json
{ "repository": { /* GitHubRepositorySummary */ }, "readme_present": true, "default_branch_sha": "abc123", "open_issues": 4, "project_id": null }
```

### `POST /projects/{project_id}/github/import` → **201**
Minimum role: `member`. Fetches normalised artefacts and stores them as `Source` rows.

Request:
```json
{
  "repository": "acme/payments",
  "include_commits": true,
  "include_issues": true,
  "include_pull_requests": true,
  "include_readme": true,
  "include_files": false,
  "include_changed_files": false,
  "max_items": 50
}
```
`max_items` 1–200. `include_changed_files` costs one extra GitHub request per record and is off by default.

Response:
```json
{
  "repository": { /* RepositoryRead */ },
  "imported": 47, "duplicates": 2, "skipped": 1, "failed": 0,
  "results": [ /* IngestionResult[] */ ]
}
```

**Errors:** revoked/invalid token → 401; inaccessible repository → 404; rate limit → 429 `rate_limited`; other GitHub faults → 502 `upstream_error`; unconfigured → 503 `not_configured`.

---

## 9. Endpoint index

| Method | Path | Min role | Purpose |
| --- | --- | --- | --- |
| GET | `/health`, `/api/v1/health` | – | Liveness |
| GET | `/health/ready`, `/api/v1/health/ready` | – | Readiness (+ dev-auth posture) |
| GET | `/api/v1/auth/me` | auth | Current user |
| POST | `/api/v1/auth/session` | auth | Sync Supabase session |
| POST | `/api/v1/workspaces` | auth | Create workspace |
| GET | `/api/v1/workspaces` | auth | List my workspaces |
| GET | `/api/v1/workspaces/{workspace_id}` | viewer | Workspace detail |
| POST | `/api/v1/projects` | member | Create project |
| GET | `/api/v1/projects` | auth | List accessible projects |
| GET | `/api/v1/projects/{project_id}` | viewer | Project detail |
| PATCH | `/api/v1/projects/{project_id}` | member | Update project |
| DELETE | `/api/v1/projects/{project_id}` | admin | Delete project |
| GET | `/api/v1/dashboard` | auth | Dashboard totals |
| POST | `/api/v1/projects/{project_id}/sources/upload` | member | Upload files |
| GET | `/api/v1/projects/{project_id}/sources` | viewer | List sources |
| GET | `/api/v1/sources/{source_id}` | viewer | Source detail |
| DELETE | `/api/v1/sources/{source_id}` | member | Delete source |
| GET | `/api/v1/github/status` | auth | Connection status |
| GET | `/api/v1/github/boundary` | auth | Integration boundary |
| POST | `/api/v1/github/connect` | auth | Begin OAuth |
| GET | `/api/v1/github/callback` | – | OAuth redirect |
| POST | `/api/v1/github/disconnect` | auth | Remove connection |
| GET | `/api/v1/github/repositories` | auth | List authorised repos |
| GET | `/api/v1/github/repository` | auth | Repo detail |
| POST | `/api/v1/projects/{project_id}/github/import` | member | Import repo artefacts |

`auth` = any authenticated principal.

---

## 10. Phase 3 (not implemented)

There are **no** claim-extraction, verification, or handover-generation endpoints. The typed contracts that Phase 3 will implement live in `app/schemas/claim.py` and `app/schemas/evidence.py` and are documented in [SCHEMAS.md](./SCHEMAS.md). The dashboard advertises them under `upcoming` only.
