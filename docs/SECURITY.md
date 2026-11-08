# Continuum — Security Review

This document describes the security controls Continuum actually enforces in its
codebase, the tests that exercise them, and the gaps that remain. Every claim
below is traceable to a source file; nothing here is aspirational.

Continuum is a FastAPI backend ([`backend/app`](../backend/app)) with a React
frontend ([`frontend/src`](../frontend/src)).

---

## 1. Overview & Threat Model

Continuum reconstructs project knowledge from authorised sources, has it verified
and approved by humans, and produces a versioned handover. The assets worth
protecting are:

| Asset | Where it lives | Primary risk |
| --- | --- | --- |
| Tenant project knowledge (claims, memory, evidence) | PostgreSQL via SQLAlchemy ORM | Cross-tenant disclosure, unauthorised modification |
| Source material (uploads, GitHub content) | DB + `storage/uploads` on disk | Hostile uploads, secret disclosure, prompt injection |
| Credentials (Supabase JWTs, GitHub OAuth tokens, model API keys) | Env vars, encrypted DB column | Token theft, at-rest exposure |
| Handover integrity (approved facts, provenance) | Immutable `HandoverVersion` rows | Fabricated facts, tampered approvals, restricted-data leakage |

Trust boundaries:

- The **browser is untrusted**. Identity is derived only from a server-verified
  token; the backend never trusts a client-supplied user id, workspace id or role
  ([`security.py`](../backend/app/core/security.py)).
- **Uploaded content and repository text are untrusted data**, never
  instructions ([`prompts.py`](../backend/app/ai/prompts.py)).
- **The AI layer is not trusted to verify.** Only a human reviewer may mark a
  claim `Verified` ([`schemas/claim.py`](../backend/app/schemas/claim.py)).

---

## 2. Authentication

### 2.1 Supabase JWT verification (two paths)

Every request resolves identity in `principal_from_token`
([`security.py`](../backend/app/core/security.py)) from a `Bearer` token. Two
server-side verification paths are supported:

- **Symmetric (HS256 family)** — when `SUPABASE_JWT_SECRET` is set, the token is
  decoded with that secret using `algorithms=["HS256", "HS384", "HS512"]`.
- **Asymmetric (RS256 / ES256 / EdDSA)** — otherwise the token is verified
  against the project's JWKS endpoint
  (`{SUPABASE_URL}/auth/v1/.well-known/jwks.json`) via a cached `PyJWKClient`.

Audience verification is enabled whenever `SUPABASE_JWT_AUDIENCE` is set (the
default is `authenticated`). Expired tokens map to `token_expired`; any other
invalid token maps to `invalid_token`. If Supabase is not configured, the server
returns a clearly-labelled `503 auth_not_configured` instead of failing open.

Identity comes **only** from the verified token's `sub` claim; a missing `sub`
is rejected. The local user record is then resolved/provisioned from that
verified identity ([`auth_service.py`](../backend/app/services/auth_service.py)).

### 2.2 Development auth bypass (gated)

A static `DEV_AUTH_TOKEN` is accepted **only** when all of the following hold
([`security.py`](../backend/app/core/security.py)):

```
settings.allow_dev_auth is True
and not settings.is_production
and token == settings.dev_auth_token
```

The bypass produces a fixed `dev-user` principal. It is disabled by default
(`allow_dev_auth: bool = False`).

### 2.3 Fail-fast production validation

`Settings._validate_environment` ([`config.py`](../backend/app/core/config.py))
raises at startup if `ENVIRONMENT=production` while `ALLOW_DEV_AUTH=true`. A
misconfigured production deployment therefore **refuses to boot** rather than
silently accepting forged dev tokens.

---

## 3. Authorisation & Tenancy

### 3.1 Isolation: 404, never 403, for invisible resources

Access resolution lives in
[`dependencies.py`](../backend/app/core/dependencies.py). When a caller is not a
member of the owning workspace, the API raises `NotFoundError` — HTTP **404** —
so a non-member cannot distinguish "does not exist" from "not permitted"
([`errors.py`](../backend/app/core/errors.py), `NotFoundError` semantics). This
applies to both `resolve_workspace_access` and `resolve_project_access`.

A caller who *is* a member but lacks sufficient rank gets a `ForbiddenError`
(403) whose `details` include their role and the required role.

### 3.2 Role hierarchy

Roles are ranked in [`permissions.py`](../backend/app/core/permissions.py):

```
viewer (1) < member (2) < admin (3) < owner (4)
```

| Role group | Members | Purpose |
| --- | --- | --- |
| `READ_ROLES` | viewer, member, admin, owner | Read workspace resources |
| `WRITE_ROLES` | member, admin, owner | Create/modify projects, ingest sources |
| `ADMIN_ROLES` | admin, owner | Delete projects, connect integrations |

`ensure_role` raises `ForbiddenError` with `required_roles` in `details`.

### 3.3 Where enforcement happens

The dependency factories in `dependencies.py` map HTTP-level access to a
required rank: `project_reader` (VIEWER), `project_writer` (MEMBER),
`project_admin` (ADMIN), `workspace_member` (MEMBER).

In the handover router ([`handover.py`](../backend/app/api/v1/handover.py)):

| Endpoint | Required |
| --- | --- |
| `POST …/handovers/generate` | MEMBER |
| `GET …/handovers`, `…/versions`, export `.md`/`.pdf`, `…/audit` | VIEWER |
| `PATCH …/handovers/{id}`, `…/submit`, `…/approve`, `…/publish`, `…/archive` | ADMIN (`_reviewer`) |
| `approve` / `publish` (service level) | OWNER or ADMIN (`PUBLISHER_ROLES`) |

The approval/publish service methods re-check the role independently
([`handover_service.py`](../backend/app/services/handover_service.py),
`PUBLISHER_ROLES`), so a caller cannot reach them merely by holding an ADMIN
route.

---

## 4. Integration Security (GitHub OAuth)

The flow is entirely server-side ([`github_service.py`](../backend/app/services/github_service.py)):

- **Tokens are encrypted at rest.** `TokenCipher` wraps `GITHUB_TOKEN_ENCRYPTION_KEY`
  (a Fernet key). Access tokens are encrypted before being stored and decrypted
  only in `_client_for` when calling GitHub.
- **Tokens never reach browser JavaScript.** The OAuth code is exchanged
  server-side; only the connection *profile* (login, avatar) is exposed through
  the status schema.
- **CSRF protection.** OAuth `state` is a short-lived (600 s) signed HS256 JWT
  bound to the authenticated user id and a nonce; the callback verifies it
  (`github_oauth` purpose check).
- **503 boundary when unconfigured.** With credentials absent,
  `ensure_configured` raises `NotConfiguredError` (HTTP 503,
  `code="github_not_configured"`) with remediation guidance — no fabricated data
  is returned.
- **Upstream rate limits surfaced.** A GitHub `403` rate-limit response is
  translated into `RateLimitError` (HTTP 429) with reset information.

---

## 5. File Ingestion Security

Implemented across [`file_parser.py`](../backend/app/services/file_parser.py),
[`ingestion_service.py`](../backend/app/services/ingestion_service.py) and
[`utils/files.py`](../backend/app/utils/files.py).

| Control | Implementation |
| --- | --- |
| Magic-byte sniffing | `detect_actual_format` inspects leading bytes (`%PDF-`, `PK\x03\x04`), not the client-declared type. A mismatch between declared extension and detected content is rejected (unless both are text-like). |
| Size cap | `MAX_UPLOAD_SIZE_BYTES` (default 25 MB); `read_limited` reads at most `max+1` bytes to detect oversize input. |
| Extension allow/deny lists | `ALLOWED_UPLOAD_EXTENSIONS` (`.pdf`, `.md`, `.markdown`, `.txt`, `.zip`); `DENIED_EXTENSIONS` (executables, archives, key material); `DENIED_FILENAMES` (`.env`, `id_rsa`, `credentials`, …). |
| ZIP path traversal | `normalize_archive_path` rejects absolute paths, drive letters, backslash escapes and `../` traversal (zip-slip). |
| ZIP expansion caps | `MAX_ZIP_EXPANSION_BYTES` (default 100 MB total), `max_zip_entries` (default 200), `max_zip_entry_bytes` (default 10 MB per entry), plus a 1000× compression-ratio guard. |
| Nesting limit | Nested archives (depth > 1) are skipped. |
| Stored, never executed | Uploaded bytes are written to disk and parsed as data streams only; nothing is executed. |

Archives are inspected member-by-member: denied paths (`.git`, `node_modules`,
…), denied filenames and disallowed extensions are skipped, and the archive
itself is stored under the project's `storage/uploads/<project_id>` directory
using a random `safe_storage_key`.

Content de-duplication is done by SHA-256 `content_hash` per project, and
detected duplicates return the original `source_id` rather than creating a copy.

---

## 6. Secret Handling

### 6.1 Scanner + redaction ([`security_scanner.py`](../backend/app/services/security_scanner.py))

The scanner runs **before** content is persisted or handed to the AI layer. It
matches a fixed catalogue of secret patterns (private keys, AWS keys, GitHub
tokens/PATs, Slack tokens/webhooks, Google API keys, Stripe keys, npm tokens,
OpenAI keys, JWTs, connection strings, bearer tokens, generic assignments).

Guarantees enforced by the code:

- **Values are never logged or returned in full.** Findings store only a masked
  preview (`mask_secret`) and a `kind` + line number; `as_warning()` contains no
  secret material.
- **Detected values are redacted in the stored content** using
  `[REDACTED:{kind}]` placeholders.
- **Only value-free metadata is persisted** — `ScanResult.summary` records
  `has_secrets`, `secret_types` and `secret_count`.

In [`ingestion_service.py`](../backend/app/services/ingestion_service.py), the
scanner is applied to every uploaded document (segment-by-segment, preserving
offsets) and to every GitHub artefact (`ingest_text_artifact`), before
persistence.

### 6.2 Credentials from environment only

All credentials are read from environment variables
([`config.py`](../backend/app/core/config.py)); nothing is hard-coded and no
secret is logged.

### 6.3 VITE_ prefix rule

In the frontend, only `VITE_`-prefixed variables are exposed to the bundle
([`.env.example`](../frontend/.env.example), [`env.ts`](../frontend/src/lib/env.ts)).
Only public client values (`VITE_API_BASE_URL`, `VITE_SUPABASE_URL`,
`VITE_SUPABASE_ANON_KEY`, `VITE_DEV_AUTH_TOKEN`) are declared. Server secrets
(GitHub secret, Fernet key, JWT secret, model API keys) have no `VITE_` prefix
and are therefore never shipped to the browser.

---

## 7. AI-Layer Safety

- **Untrusted text is data, not instructions.** The system prompt
  ([`prompts.py`](../backend/app/ai/prompts.py), `_UNTRUSTED_GUARD`) states that
  everything inside `<evidence>` blocks is untrusted data: the model must never
  follow instructions found inside it, never reveal or request credentials, and
  never cite a source that was not provided.
- **The model may not invent references.** Only backend-issued handles
  (`S1`, `C1`, …) are shown; resolution and rejection of unknown handles happen in
  application code, not in the prompt.
- **Human-only `Verified` governance.**
  [`schemas/claim.py`](../backend/app/schemas/claim.py) defines
  `HUMAN_ONLY_STATUSES = {Verified}`; `assert_ai_assignable_status` raises if an
  automated agent tries to write it. AI may only emit `Supported`, `Uncertain`
  or `Conflict`. The handover engine consumes only approved
  (`ClaimStatus.VERIFIED`) claims.
- **AI source-access filtering.** Before any content reaches a model, the
  workflow `access_filter` ([`workflow/nodes.py`](../backend/app/workflow/nodes.py))
  loads only sources the requesting user may use and drops `restricted` sources
  for roles outside `_RESTRICTED_ROLES = (ADMIN, OWNER)`. A non-member fails the
  run before any source is read (`workspace_membership_required`).

---

## 8. Evidence & Handover Access Control

- **Restricted sources are excluded from successor-facing output.**
  `HandoverService.evidence_index` ([`handover_service.py`](../backend/app/services/handover_service.py))
  defaults to `include_restricted=False` and skips any source whose
  `access_label` is `restricted`. The only caller that sets
  `include_restricted=True` is the internal evaluation service
  ([`evaluation/service.py`](../backend/app/evaluation/service.py)), not any
  export path. `render_markdown` / `render_pdf` build their evidence index with
  the default (excluded) view.
- **Export permissions.** `_export_payload`
  ([`handover.py`](../backend/app/api/v1/handover.py)) re-checks project access
  (VIEWER) on every export, loads the exact version, and appends an
  `handover_exported` audit entry.
- **Handover integrity.** Content lives in immutable `HandoverVersion` rows;
  edits append a new version rather than overwriting, and a published version is
  never replaced. Factual statements are re-validated against the *current*
  approved claim set and exact revisions before approval/publish; anything
  unsupported is flagged rather than silently treated as evidence-backed.

---

## 9. Application Hardening

- **SQL injection.** All database access goes through SQLAlchemy 2 ORM /
  parameterised queries. A search for raw `text(...)` SQL finds only
  `text("SELECT 1")` in the health probes
  ([`health.py`](../backend/app/api/v1/health.py),
  [`readiness.py`](../backend/app/api/v1/readiness.py)) and JSONB
  `server_default` literals in the model layer — no string-built queries.
- **XSS.** The frontend renders with React (auto-escaping). A search for
  `dangerouslySetInnerHTML` across `frontend/src` returns no matches.
- **Error envelope leaks nothing.** Every error uses one stable envelope
  `{"error": {"code", "message", "details"}}`
  ([`errors.py`](../backend/app/core/errors.py)). Unhandled exceptions are
  logged server-side (type + traceback) but the client receives a generic
  `internal_error` with no stack trace or internal detail. 404 vs 403 semantics
  keep other tenants' resources invisible.
- **Correlation ids.** `CorrelationIdMiddleware`
  ([`main.py`](../backend/app/main.py)) takes `X-Request-ID` from the inbound
  request (or generates one), logs a single structured line per request with
  method, path, status and duration, and echoes the id on the response header.
- **Configuration posture only.** The readiness probe reports configuration
  booleans (`supabase_auth_configured`, `github_oauth_configured`,
  `dev_auth_enabled`) — never the underlying values.
- **CORS.** Origins are configuration-driven (defaults to localhost dev
  origins); the `X-Request-ID` header is the only exposed header.

---

## 10. Tested Controls

The following table maps controls to the test files that exercise them. Only
scenarios present in the named tests are listed.

| Control | Test file / scenario |
| --- | --- |
| ZIP path traversal (zip-slip) rejection | [`tests/test_security.py`](../backend/tests/test_security.py) — `test_zip_slip_entry_is_rejected_but_safe_entries_ingest` (`../escape.md` fails, `notes.md` ingests) |
| Archive deny lists + nested-archive skip | `test_security.py` — `test_zip_denied_paths_and_nested_archives_are_skipped` (`node_modules/…`, `.env`, `inner.zip` skipped; `docs/guide.md` ingests) |
| Absolute archive path rejection | `test_security.py` — `test_absolute_archive_path_is_rejected` (`/etc/passwd`) |
| Secret redaction without leaking values | `test_security.py` — `test_scanner_redacts_without_leaking_values`, `test_scanner_leaves_benign_text_untouched` |
| Secrets redacted before storage | `test_security.py` — `test_uploaded_secret_is_redacted_before_storage` (GitHub token + password absent from stored content; `security_scan.has_secrets` true) |
| Restricted-source role matrix | [`tests/test_permissions_matrix.py`](../backend/tests/test_permissions_matrix.py) — `test_restricted_sources_follow_the_role_matrix` (owner/admin see, member/viewer do not) |
| Restricted roles are admin/owner only | `test_permissions_matrix.py` — `test_only_admin_and_owner_may_see_restricted_sources` |
| Restricted content never reaches the model | `test_permissions_matrix.py` — `test_restricted_content_never_reaches_the_model` |
| Non-member refused before any source is read | `test_permissions_matrix.py` — `test_a_non_member_is_refused_before_any_source_is_read` |
| Prompt-injection resistance (fencing + guard) | [`tests/test_prompt_injection.py`](../backend/tests/test_prompt_injection.py) — `test_evidence_is_fenced_and_the_system_prompt_calls_it_untrusted` |
| No credential in any prompt | `test_prompt_injection.py` — `test_no_credential_is_ever_placed_in_a_prompt`, and the prompt/system assertion in `test_injected_instructions_are_preserved_as_data_and_not_obeyed` |
| Injection treated as inert data; fabricated citation rejected | `test_prompt_injection.py` — `test_injected_instructions_are_preserved_as_data_and_not_obeyed` (claim typed `other`; `claim_evidence_unknown`) |
| PDF/Markdown/TXT ingestion | [`tests/test_uploads.py`](../backend/tests/test_uploads.py) — `test_upload_pdf_is_parsed_and_persisted`, `test_upload_markdown_captures_headings`, `test_upload_text_captures_line_numbers` |
| Unsupported extension rejected | `test_uploads.py` — `test_unsupported_extension_is_rejected` (`malware.exe`) |
| Deny-listed filename refused | `test_uploads.py` — `test_deny_listed_filename_is_refused` (`id_rsa`) |
| Declared type must match content | `test_uploads.py` — `test_declared_extension_must_match_content` (`fake.pdf` with text body) |
| Empty / oversized upload rejected | `test_uploads.py` — `test_empty_file_is_rejected`, `test_oversized_upload_is_rejected` (422 `validation_error`) |
| Content de-duplication | `test_uploads.py` — `test_duplicate_content_is_detected` |

Additional access-control assertions (HTTP 403 / 404 / `not_found`) also appear
across [`test_auth.py`](../backend/tests/test_auth.py),
[`test_workspaces.py`](../backend/tests/test_workspaces.py),
[`test_projects.py`](../backend/tests/test_projects.py),
[`test_sources.py`](../backend/tests/test_sources.py),
[`test_github.py`](../backend/tests/test_github.py) and
[`test_phase4_review_handover.py`](../backend/tests/test_phase4_review_handover.py).

---

## 11. Known Gaps & Recommendations

The following are **not** implemented in the current codebase. Each item was
verified before being listed.

1. **No general API rate limiting.** There is no application-wide rate-limiting
   middleware or dependency (no `slowapi`/limiter is present). Rate-limit
   handling exists only for *upstream* providers: a GitHub `403` rate-limit and
   the model provider's `429` are mapped to a `429 rate_limited` response
   ([`errors.py`](../backend/app/core/errors.py),
   [`github_service.py`](../backend/app/services/github_service.py),
   [`ai/provider.py`](../backend/app/ai/provider.py)). Own API endpoints —
   including login-adjacent and upload endpoints — are not throttled.
   *Recommendation: add a per-identity/IP limiter at the edge or via middleware.*
2. **No WAF / DDoS protection at the application layer.** Protection depends
   entirely on the deployment environment. *Recommendation: front the service
   with a WAF/CDN or reverse-proxy rate limiting.*
3. **Uploaded archive bytes are stored unencrypted.** For ZIP uploads, the raw
   archive is persisted to disk under `storage/uploads/<project_id>`
   ([`ingestion_service.py`](../backend/app/services/ingestion_service.py),
   `_store_bytes`). Redaction applies to the normalised content stored in the
   database, but the raw archive blob on disk retains the original bytes.
   *Recommendation: encrypt or delete raw archives after parsing, or run the
   secret scan on the raw bytes before persisting.*
4. **Frontend token storage in `localStorage`.**
   [`session.ts`](../frontend/src/lib/session.ts) mirrors the access token to
   `localStorage` (and memory), which is readable by any script running on the
   origin. The backend independently re-verifies every request, limiting blast
   radius, but a successful XSS would expose the token.
   *Recommendation: consider httpOnly cookie-based sessions or short-lived
   tokens with refresh, and a strict Content-Security-Policy.*
5. **No CSP / security headers configured.** No `Content-Security-Policy`,
   `X-Content-Type-Options` or similar response headers are set by the backend
   ([`main.py`](../backend/app/main.py)) or the frontend build.
   *Recommendation: add security headers at the edge or via middleware.*
6. **No documented dependency-vulnerability scanning.** No automated
   `pip-audit`/`npm audit` gate is wired into the repository.
   *Recommendation: add dependency scanning to CI.*
7. **Dev auth token default is a shared constant.** `dev_auth_token` defaults to
   `"dev-local-token"` ([`config.py`](../backend/app/core/config.py)). It is
   gated by `ALLOW_DEV_AUTH` + non-production, but a weak default in a
   non-production-but-reachable environment is a residual risk.
   *Recommendation: require an explicit, non-default value whenever
   `ALLOW_DEV_AUTH` is enabled.*
