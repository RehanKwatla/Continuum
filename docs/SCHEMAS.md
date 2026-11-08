# Continuum — Data Schemas

Phase 1 (Foundation) + Phase 2 (Source Ingestion), plus the shared contracts that Phase 3 will implement.

> Governance rule encoded in the schema layer: **only a human reviewer may set a claim to `Verified`. Automated agents may never approve a claim.**

---

## 1. Conventions

- **Primary keys:** every table uses a UUID primary key (`id UUID PRIMARY KEY`, generated server-side).
- **Timestamps:** `created_at` / `updated_at` are `TIMESTAMPTZ NOT NULL`.
- **Foreign keys:** declared with `ON DELETE CASCADE` for owning relationships, `ON DELETE SET NULL` for the audit log so history survives row deletion.
- **Enums:** stored as PostgreSQL `ENUM` types (named per column, e.g. `source_type`, `claim_status`).
- **Indexes:** every foreign key is indexed; composite indexes cover the common access paths (see each table).
- **`metadata`:** the JSON column is named `metadata` in the database but the ORM attribute is `meta` (`metadata` is reserved by SQLAlchemy). All JSON columns are `NOT NULL DEFAULT '{}'` or `'[]'`.
- **pgvector:** the `vector` extension is installed at database initialisation (`docker/init/01_extensions.sql`). **No embedding column is currently defined** — inventing embeddings is explicitly out of scope for Phase 1/2. The extension is provisioned so Phase 3 can add a vector column via a new migration without re-provisioning the database.
- **Migrations:** all schema changes go through Alembic (`backend/alembic/`). Initial revision: `de0d374b689f_initial_continuum_schema`.

---

## 2. The 8 core entities

### 2.1 `users`

Identity is ultimately owned by Supabase Auth; this table holds the local projection.

| Column | Type | Constraints |
| --- | --- | --- |
| `id` | UUID | PK |
| `email` | VARCHAR(320) | NOT NULL, UNIQUE, indexed |
| `full_name` | VARCHAR(255) | NULL |
| `supabase_user_id` | VARCHAR(64) | NULL, UNIQUE, indexed — the Supabase `sub`; NULL for development-only identities |
| `created_at` | TIMESTAMPTZ | NOT NULL |

Relationships: `memberships` → `workspace_members`; `owned_workspaces` → `workspaces`.

### 2.2 `workspaces`

| Column | Type | Constraints |
| --- | --- | --- |
| `id` | UUID | PK |
| `name` | VARCHAR(200) | NOT NULL |
| `owner_id` | UUID | FK → `users.id` ON DELETE CASCADE, indexed |
| `created_at` | TIMESTAMPTZ | NOT NULL |

Relationships: `owner`, `members` (cascade), `projects` (cascade).

### 2.3 `workspace_members`

The join between a user and a workspace, carrying their role. Unique per `(workspace_id, user_id)`.

| Column | Type | Constraints |
| --- | --- | --- |
| `id` | UUID | PK |
| `workspace_id` | UUID | FK → `workspaces.id` CASCADE, indexed |
| `user_id` | UUID | FK → `users.id` CASCADE, indexed |
| `role` | `workspace_role` enum | NOT NULL — `owner` \| `admin` \| `member` \| `viewer` |
| `created_at` | TIMESTAMPTZ | NOT NULL |

Unique constraint: `uq_workspace_members_workspace_user (workspace_id, user_id)`.

**Role ranks** (used by `app/core/permissions.py::has_at_least`): `viewer` < `member` < `admin` < `owner`.

### 2.4 `projects`

| Column | Type | Constraints |
| --- | --- | --- |
| `id` | UUID | PK |
| `workspace_id` | UUID | FK → `workspaces.id` CASCADE, indexed |
| `name` | VARCHAR(200) | NOT NULL |
| `description` | TEXT | NULL |
| `status` | `project_status` enum | NOT NULL, default `active`, indexed — `draft` \| `active` \| `handover_in_progress` \| `handed_over` \| `archived` |
| `departing_role` | VARCHAR(120) | NULL |
| `successor_role` | VARCHAR(120) | NULL |
| `created_at` | TIMESTAMPTZ | NOT NULL |
| `updated_at` | TIMESTAMPTZ | NOT NULL |

Composite index: `ix_projects_workspace_status (workspace_id, status)`.
Relationships: `workspace`, `sources` (cascade), `repositories` (cascade).

### 2.5 `sources`

The normalised unit of ingested knowledge — one row per document, commit, issue, PR, README or file.

| Column | Type | Constraints |
| --- | --- | --- |
| `id` | UUID | PK |
| `project_id` | UUID | FK → `projects.id` CASCADE, indexed |
| `source_type` | `source_type` enum | NOT NULL, indexed |
| `source_name` | VARCHAR(500) | NOT NULL |
| `external_id` | VARCHAR(300) | NULL, indexed — identifier in the origin system (commit SHA, issue number, archive path) |
| `content` | TEXT | NULL — normalised, secret-redacted text |
| `metadata` | JSONB | NOT NULL, default `{}` — character/segment counts, `security_scan` summary, parse warnings |
| `author` | VARCHAR(255) | NULL |
| `created_at_source` | TIMESTAMPTZ | NULL — timestamp **at the origin**, may differ from ingestion time |
| `access_label` | `access_label` enum | NOT NULL, default `workspace` |
| `processing_status` | `processing_status` enum | NOT NULL, default `pending`, indexed |
| `content_hash` | VARCHAR(64) | NULL, indexed — SHA-256 of the normalised content |
| `storage_key` | VARCHAR(255) | NULL — random key of the archived raw upload |
| `mime_type` | VARCHAR(120) | NULL |
| `size_bytes` | BIGINT | NULL |
| `source_url` | VARCHAR(1000) | NULL |
| `error_message` | TEXT | NULL |
| `warnings` | JSONB | NOT NULL, default `[]` |
| `created_at` | TIMESTAMPTZ | NOT NULL |

Composite indexes: `ix_sources_project_type (project_id, source_type)`, `ix_sources_project_status (project_id, processing_status)`.
Unique constraint: `uq_sources_project_content_hash (project_id, content_hash)` — this is the **duplicate-detection** mechanism.

**Enumerations**

`source_type`: `github_commit`, `github_issue`, `github_pull_request`, `github_readme`, `github_file`, `uploaded_pdf`, `uploaded_markdown`, `uploaded_text`, `uploaded_zip_entry`.

`processing_status`: `pending`, `processing`, `completed`, `failed`, `skipped`, `duplicate`.

`access_label`: `workspace`, `private`, `public`, `restricted`.

Relationship: `evidence` → `evidence` (cascade).

### 2.6 `claims`

A knowledge assertion awaiting evidence and human review. **The AI layer may only ever write `Supported`, `Uncertain` or `Conflict`** (see §4).

| Column | Type | Constraints |
| --- | --- | --- |
| `id` | UUID | PK |
| `project_id` | UUID | FK → `projects.id` CASCADE, indexed |
| `text` | TEXT | NOT NULL |
| `claim_type` | `claim_type` enum | NOT NULL, default `other` |
| `entity` | VARCHAR(300) | NULL — primary entity the claim is about |
| `status` | `claim_status` enum | NOT NULL, default `Uncertain`, indexed |
| `critical` | BOOLEAN | NOT NULL, default `false` |
| `created_at` | TIMESTAMPTZ | NOT NULL |

Composite index: `ix_claims_project_status (project_id, status)`.
Relationship: `evidence` → `evidence` (cascade).

`claim_type`: `decision`, `architecture`, `process`, `constraint`, `risk`, `contact`, `status`, `other`.
`claim_status`: `Supported`, `Uncertain`, `Conflict`, `Verified`.

### 2.7 `evidence`

Links a claim to the exact span of a source that supports or contradicts it.

| Column | Type | Constraints |
| --- | --- | --- |
| `id` | UUID | PK |
| `claim_id` | UUID | FK → `claims.id` CASCADE, indexed |
| `source_id` | UUID | FK → `sources.id` CASCADE, indexed |
| `source_location` | VARCHAR(500) | NULL — human-readable locator, e.g. `README.md#L12-L18` or `page 3` |
| `start_offset` | INTEGER | NULL |
| `end_offset` | INTEGER | NULL |
| `supporting_quote` | TEXT | NULL |
| `created_at` | TIMESTAMPTZ | NOT NULL |

Composite index: `ix_evidence_claim_source (claim_id, source_id)`.

### 2.8 `audit_logs`

Append-only record of security-relevant actions (workspace/project/source/membership events).

| Column | Type | Constraints |
| --- | --- | --- |
| `id` | UUID | PK |
| `user_id` | UUID | FK → `users.id` ON DELETE SET NULL, indexed |
| `workspace_id` | UUID | FK → `workspaces.id` ON DELETE SET NULL, indexed |
| `action` | VARCHAR(100) | NOT NULL, indexed — e.g. `source.deleted` |
| `resource_type` | VARCHAR(50) | NULL |
| `resource_id` | UUID | NULL (no FK — survives the referenced row) |
| `metadata` | JSONB | NOT NULL, default `{}` |
| `created_at` | TIMESTAMPTZ | NOT NULL |

Composite index: `ix_audit_logs_workspace_created (workspace_id, created_at)`.

---

## 3. Supporting tables (Phase 2 integrations)

### 3.1 `github_connections`

One per user. The access token is **Fernet-encrypted at rest** and is never returned by the API.

| Column | Type | Constraints |
| --- | --- | --- |
| `id` | UUID | PK |
| `user_id` | UUID | FK → `users.id` CASCADE, UNIQUE, indexed |
| `github_user_id` | VARCHAR(64) | NULL |
| `github_login` | VARCHAR(120) | NULL |
| `github_avatar_url` | VARCHAR(500) | NULL |
| `encrypted_access_token` | TEXT | NOT NULL |
| `token_type` | VARCHAR(32) | NOT NULL, default `bearer` |
| `scopes` | VARCHAR(500) | NULL |
| `connected_at` | TIMESTAMPTZ | NOT NULL |
| `updated_at` | TIMESTAMPTZ | NOT NULL |

### 3.2 `project_repositories`

A repository connected to a project (Phase 2: GitHub only).

| Column | Type | Constraints |
| --- | --- | --- |
| `id` | UUID | PK |
| `project_id` | UUID | FK → `projects.id` CASCADE, indexed |
| `provider` | VARCHAR(32) | NOT NULL, default `github` |
| `full_name` | VARCHAR(300) | NOT NULL — `owner/name` |
| `external_id` | VARCHAR(64) | NULL |
| `description` | TEXT | NULL |
| `default_branch` | VARCHAR(200) | NULL |
| `is_private` | BOOLEAN | NOT NULL, default `false` |
| `html_url` | VARCHAR(500) | NULL |
| `metadata` | JSONB | NOT NULL, default `{}` |
| `connected_at` | TIMESTAMPTZ | NOT NULL |

Unique constraint: `uq_project_repositories_project_provider_name (project_id, provider, full_name)`.

---

## 4. Claim & Verification contracts *(shared with Phase 3)*

These Pydantic v2 models in `app/schemas/claim.py` and `app/schemas/evidence.py` are the interface the Phase 3 Extractor, Verifier and Handover-Writer agents must implement. **No agent is implemented in Phase 1/2**, and nothing in the current codebase fabricates claims or evidence.

### 4.1 `Claim`

| Field | Type | Default | Notes |
| --- | --- | --- | --- |
| `id` | UUID | – | |
| `text` | string (min 1) | – | Short, self-contained assertion. |
| `claim_type` | `ClaimType` | `other` | |
| `entity` | string \| null | null | Module, service, owner… |
| `source_span_ids` | UUID[] | `[]` | Evidence ids backing the claim. |
| `access_label` | `AccessLabel` | `workspace` | |
| `critical` | bool | `false` | |
| `status` | `ClaimStatus` | `Uncertain` | |

`ClaimStatus` values: **`Supported`**, **`Uncertain`**, **`Conflict`**, **`Verified`**.

### 4.2 `Verification`

| Field | Type | Notes |
| --- | --- | --- |
| `claim_id` | UUID | |
| `verdict` | `VerificationVerdict` | `supports` \| `partly` \| `none` |
| `supporting_quote` | string \| null | |
| `contradicted_by` | UUID[] | Evidence ids that contradict the claim. |
| `reasoning` | string \| null | |
| `confidence` | float 0–1 \| null | |

### 4.3 `Evidence` / `EvidenceBundle`

- `EvidenceCreate` / `EvidenceRead` mirror the `evidence` table (§2.7).
- `EvidenceBundle` groups evidence **per claim** into `supporting[]` and `contradicting[]` — the shape the Handover Writer will consume.

### 4.4 The human-verification rule (enforced in code)

```python
AI_ASSIGNABLE_STATUSES = {Supported, Uncertain, Conflict}
HUMAN_ONLY_STATUSES    = {Verified}

def assert_ai_assignable_status(status: ClaimStatus) -> None:
    if status in HUMAN_ONLY_STATUSES:
        raise ValueError(
            f"Status '{status.value}' can only be set by a human reviewer; "
            "automated agents may not verify claims."
        )
```

- `ClaimExtractionResult` is the structured output contract for the Phase 3 **Extractor**.
- `Verification` is the structured output contract for the Phase 3 **Verifier**.
- Any automated pipeline that calls `assert_ai_assignable_status(Verified)` will raise — the AI layer cannot approve a claim, by construction.

---

## 5. Entity relationship overview

```
users ──1:N── workspace_members ──N:1── workspaces
  │                                        │
  │ owner                                  │ 1:N
  └────────────────────────────────────► projects ──1:N── sources ──1:N── evidence ──N:1── claims
                                            │                                              │
                                            └──1:N── project_repositories                  └── project_id
users ──1:1── github_connections
users / workspaces ──N:1── audit_logs   (append-only)
```

---

## 6. Migration & verification commands

```bash
# Apply every migration (run from backend/)
alembic upgrade head

# Create a new revision after editing models
alembic revision --autogenerate -m "describe change"

# Confirm the schema matches the models used by the test-suite
python -m pytest tests/test_health.py -q
```

The test suite creates the schema from the SQLAlchemy metadata (`Base.metadata.create_all`) against a real PostgreSQL database with the real `pgvector`/`uuid` extensions — there is no SQLite fallback and no mocked persistence.
