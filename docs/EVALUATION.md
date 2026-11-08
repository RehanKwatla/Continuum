# CONTINUUM — Evaluation Framework

This document describes the evaluation subsystem of CONTINUUM: the synthetic
ground-truth dataset, the reproducible metrics (A–I), how an evaluation run is
executed and persisted, how runs are compared for regressions, and the
deterministic successor readiness exercise (§10).

Everything below is derived directly from the source code. No scores are
invented here; the framework reports what the live pipeline actually produced
measured against the ground truth.

Source files:

- [`backend/app/evaluation/ground_truth.py`](../backend/app/evaluation/ground_truth.py)
- [`backend/app/evaluation/metrics.py`](../backend/app/evaluation/metrics.py)
- [`backend/app/evaluation/service.py`](../backend/app/evaluation/service.py)
- [`backend/app/evaluation/synthetic.py`](../backend/app/evaluation/synthetic.py)
- [`backend/app/services/continuity_service.py`](../backend/app/services/continuity_service.py) (§8 scorecard, §10 exercise)
- [`backend/app/models/phase5.py`](../backend/app/models/phase5.py) (`EvaluationRun`)
- [`backend/app/api/v1/readiness.py`](../backend/app/api/v1/readiness.py) (endpoints)
- [`backend/tests/test_phase5_evaluation.py`](../backend/tests/test_phase5_evaluation.py)

---

## 1. Purpose & principles

The evaluation subsystem answers one question honestly: **given a project whose
correct output is known, how well did the real pipeline do?**

Principles enforced by the code:

1. **Reproducible.** Metrics are pure functions of already-loaded data
   ([`metrics.py`](../backend/app/evaluation/metrics.py) never reads the
   database, calls a model, or invents a number). The service reads the real
   database state, applies those functions, and persists the result as an
   immutable `EvaluationRun`. Repeated runs on unchanged data produce identical
   metrics.

2. **No fabricated scores.** Every ratio is `0.0` when its denominator is zero,
   and the result carries `undefined: True` in that case, so a "0/0" is never
   silently presented as a real score (see `_ratio` in
   [`metrics.py`](../backend/app/evaluation/metrics.py)).

3. **Ground truth is separate from the system's outputs.** The ground-truth
   dataset ([`ground_truth.py`](../backend/app/evaluation/ground_truth.py))
   is authored as a product-owned reference dataset — nothing in it is generated
   by a model. The evaluation reads the real database rows back (`observe`) and
   scores them *against* these expectations. It is the yardstick, not the
   result.

4. **Metric functions are pure and independently testable.** The unit tests in
   [`test_phase5_evaluation.py`](../backend/tests/test_phase5_evaluation.py)
   drive them directly with hand-built datasets and observations.

---

## 2. The synthetic ground-truth dataset

Defined in [`ground_truth.py`](../backend/app/evaluation/ground_truth.py) and
seeded by [`synthetic.py`](../backend/app/evaluation/synthetic.py).

| Item | Value |
| --- | --- |
| Ground-truth version | `GROUND_TRUTH_VERSION = "continuum-ground-truth-v1"` |
| Project name | `GROUND_TRUTH_PROJECT_NAME = "Payments Service Handover (ground truth)"` |
| Scenario | "Payments Service" handover |

### What the dataset contains

**8 ground-truth claims** (each with `claim_type`, `entity`, `keywords`,
`evidence_source`, and flags):

| Key | Text | Type | Evidence source | Critical |
| --- | --- | --- | --- | --- |
| `db_version_13` | The production database is PostgreSQL 13. | `technical_constraint` | `architecture-notes.md` | yes |
| `db_version_15` | The production database is PostgreSQL 15. | `technical_constraint` | `commit 9f8c2ab` | yes |
| `owner_alice` | The payments module is owned by Alice. | `ownership` | `architecture-notes.md` | no |
| `owner_bob` | The payments module is owned by Bob. | `ownership` | `commit 9f8c2ab` | no |
| `retry_cap` | Webhook retries are capped at three attempts. | `technical_constraint` | `issue #412` | yes |
| `invoices_migration` | The legacy invoices table still needs to be migrated. | `unfinished_work` | `commit 9f8c2ab` | no |
| `fraud_question` | Which team owns the fraud scoring service? | `open_question` | `issue #412` | no |
| `deployment_procedure` | Deployment runs the release script on the release host. | `operational_procedure` | `README.md` | no |

**1 conflict** — `db_version_13` vs `db_version_15`, disagreeing about
`property_key = "database"` with `kind = "value_disagreement"`. This is the
database-version contradiction.

**Ownership transition (not a conflict)** — `owner_alice` → `owner_bob`. An
ownership change over time is deliberately *not* modelled as a contradiction.

**Stale source** — `stale_sources = ("README.md",)`. The README is stale
because a newer commit changed it.

**Restricted source** — `restricted_source = "restricted-credentials.md"`. This
must never appear in a successor-facing evidence index.

**4 deliberately missing-knowledge gaps**:

| requirement_id | category | description |
| --- | --- | --- |
| `ops.rollback_procedure` | rollback | No rollback procedure is documented. |
| `ops.incident_procedure` | operations | No incident or escalation procedure is documented. |
| `decisions.documented` | decisions | No important project decision is documented. |
| `risk.risks_documented` | risks | No critical risk is documented. |

**Readiness expectations** — the same four requirements are labelled with the
completion a correct engine must report: `RequirementCompletion.MISSING`.

### How it is seeded

`seed_synthetic_evaluation_project` in
[`synthetic.py`](../backend/app/evaluation/synthetic.py) creates the *inputs*
only — a workspace `Project` plus its source corpus (`SYNTHETIC_SOURCES`). It
does **not** create claims; those must come out of the real reconstruction
pipeline, which is exactly what the evaluation measures.

The 5 seeded sources (ingestion order):

| source_name | type | author | created_at_source | notes |
| --- | --- | --- | --- | --- |
| `architecture-notes.md` | uploaded markdown | alice | 2024-02-10 | states PostgreSQL 13 / owned by Alice |
| `commit 9f8c2ab` | GitHub commit | bob | 2024-06-01 | states PostgreSQL 15 / owned by Bob / invoices migration |
| `README.md` | GitHub README | alice | 2024-01-05 | deployment via release script (stale) |
| `issue #412` | GitHub issue | carol | 2024-07-15 | retry cap (three attempts) / fraud scoring question |
| `restricted-credentials.md` | uploaded markdown | alice | 2024-03-02 | restricted access label |

Seeded via `POST /api/v1/workspaces/{workspace_id}/evaluation/synthetic-project`
(workspace-scoped, `ADMIN` required). It returns the new project id, name,
`len(SYNTHETIC_SOURCES)` and `dataset_version = GROUND_TRUTH.version`.

---

## 3. Metric definitions (A–I)

All metrics are implemented in [`metrics.py`](../backend/app/evaluation/metrics.py)
and assembled by `compute_all`. Shared building blocks:

- `precision = tp / (tp + fp)`
- `recall = tp / (tp + fn)`
- `f1 = 2 * precision * recall / (precision + recall)` (computed as `2*tp / (2*tp + fp + fn)`)
- `accuracy = correct / evaluated`
- Any ratio whose denominator is `<= 0` returns `0.0` with `undefined: True`.

**Matching rule.** A ground-truth claim is *matched* when an observed claim has
the same `claim_type` **and** its `text + entity` (case-folded) contains at least
one of the ground-truth claim's `keywords`. Keywords are used deliberately so
that extraction may phrase a fact differently while still counting as captured.

The `value` field of each metric is the single headline number; the result dict
also carries the counts that produced it.

### A. `A_claim_extraction` — precision / recall / F1 of extracted claims

- **Measures:** whether the pipeline extracted the ground-truth facts and
  whether it extracted spurious claims.
- **Numerator / denominator:**
  - `precision = tp / (tp + fp)`
  - `recall = tp / (tp + fn)`
  - `f1 = 2*tp / (2*tp + fp + fn)`
  - `tp` = number of matched ground-truth claims; `fn = expected_total - tp`;
    `fp` = observed claims not matched to any ground-truth claim.
- **`value`** = `precision`.
- **Direction:** higher is better.

### B. `B_evidence_accuracy` — cited source actually supports the claim

- **Measures:** does the source the pipeline cited for a matched claim actually
  match the ground-truth `evidence_source`?
- **Formula:** `value = correct / evaluated`, where `evaluated` = matched
  claims count, and `correct` counts matched claims whose cited
  `evidence_sources` contain the ground-truth `evidence_source`.
- **Numerator / denominator:** correct citations / all evaluated cited claims.
- **Direction:** higher is better.

### C. `C_verification_accuracy` — verifier verdict matches expectation

- **Measures:** does the verifier reach the right verdict for each matched
  claim?
- **Formula:** `value = correct / evaluated`, where `evaluated` = matched
  claims **with a non-`None` verdict**, and `correct` = verdict equals the
  claim's `expected_verdict` (default `"supports"`).
- **Numerator / denominator:** correct verdicts / matched claims with a verdict.
- **Direction:** higher is better.

### D. `D_conflict_detection` — conflict precision / recall

- **Measures:** whether the pipeline detected the ground-truth contradiction
  (and did not invent conflicts).
- **Formula:** pairs are compared as `frozenset({claim_id, claim_id})`.
  `precision = tp / (tp + fp)`, `recall = tp / (tp + fn)`.
- **Numerator / denominator:** `tp` = expected conflict pairs also observed;
  `fp` = observed pairs not expected; `fn` = expected pairs not observed.
- **`value`** = `precision`.
- **Direction:** higher is better.

### E. `E_stale_detection` — stale-source detection recall

- **Measures:** whether stale sources were flagged.
- **Formula:** set comparison of expected vs observed stale sources.
  `precision = tp / (tp + fp)`, `recall = tp / (tp + fn)`.
- **Numerator / denominator:** `tp` = expected stale sources also flagged;
  `fp` = flagged but not expected; `fn` = expected but not flagged.
- **`value`** = `recall` (note: **not** precision — `value` is the recall).
- **Direction:** higher is better.

### F. `F_critical_knowledge_coverage` — critical claims present & approved

- **Measures:** how much of the critical ground-truth knowledge is present, and
  how much is present *and approved* (`status == VERIFIED`).
- `present_coverage = present / critical_total`
- `approved_coverage = approved / critical_total`
- `critical_total` = number of ground-truth claims with `critical = True` (3 in
  the dataset).
- **`value`** = `approved_coverage`.
- **Direction:** higher is better.

### G. `G_unsupported_handover_rate` — unsupported evidence-backed statements

- **Measures:** of the handover statements that are evidence-backed (status
  `established_fact`), what fraction are still flagged as unsupported?
- **Formula:** `value = unsupported / evidence_backed_statements`, where
  `evidence_backed_statements` = handover statements with `evidence_backed`;
  `unsupported` = those also flagged `unsupported`.
- **Numerator / denominator:** unsupported / evidence-backed statements.
- **Direction:** **inverted — lower is better**
  (`INVERTED_METRICS = ("G_unsupported_handover_rate",)`).

### H. `H_permission_leakage` — restricted source must be hidden by default

- **Measures:** a restricted source must be hidden from the default evidence
  index and present only with explicit restricted access.
- **Formula:** two boolean checks:
  1. `restricted_source_hidden_by_default`: restricted source **not** in
     `visible_evidence_sources`.
  2. `restricted_source_present_with_explicit_access`: restricted source **is**
     in `all_evidence_sources`.
  `value = 1.0` if both pass, else `0.0`.

  If the dataset has no restricted source, it returns `value = 1.0`,
  `passed = True`, `undefined = True`.
- **Direction:** higher is better (it is a pass/fail gate, reported outside the
  headline set; see §4).

### I. `I_readiness_agreement` — readiness vs human labels

- **Measures:** agreement between the engine's reported requirement completion
  and the dataset's human-labelled expectations.
- **Formula:** `value = agree / evaluated`, where `evaluated` =
  `len(readiness_expectations)` and `agree` counts requirements whose observed
  completion equals the expected completion value.
- **Numerator / denominator:** agreeing requirements / labelled expectations.
  With no expectations, returns `value = 0.0`, `undefined = True`.
- **Direction:** higher is better.

### Headline & inverted sets

Defined in [`metrics.py`](../backend/app/evaluation/metrics.py):

```python
HEADLINE_METRICS: tuple[str, ...] = (
    "A_claim_extraction",
    "B_evidence_accuracy",
    "C_verification_accuracy",
    "D_conflict_detection",
    "E_stale_detection",
    "F_critical_knowledge_coverage",
    "I_readiness_agreement",
)

INVERTED_METRICS: tuple[str, ...] = ("G_unsupported_handover_rate",)
```

`H_permission_leakage` is not in either tuple; the service adds it explicitly to
the persisted `metrics` (see §4).

### Summary table

| Key | Measures | Numerator / denominator | `value` is | Direction |
| --- | --- | --- | --- | --- |
| `A_claim_extraction` | claims extracted | matched / (matched+fp); matched / (matched+fn) | precision | higher better |
| `B_evidence_accuracy` | cited source correctness | correct citations / evaluated citations | value | higher better |
| `C_verification_accuracy` | verdict correctness | correct verdicts / evaluated verdicts | value | higher better |
| `D_conflict_detection` | conflict detection | tp / (tp+fp) | precision | higher better |
| `E_stale_detection` | stale-source detection | tp / (tp+fn) | recall | higher better |
| `F_critical_knowledge_coverage` | critical knowledge approved | approved / critical_total | approved coverage | higher better |
| `G_unsupported_handover_rate` | unsupported evidence-backed statements | unsupported / evidence-backed | rate | **lower better** |
| `H_permission_leakage` | restricted source hidden | 2 boolean checks | 1.0 / 0.0 | higher better |
| `I_readiness_agreement` | readiness vs labels | agree / evaluated | rate | higher better |

---

## 4. How a run works (observe → compute → persist)

`EvaluationService.run_metrics` in
[`service.py`](../backend/app/evaluation/service.py):

1. **Observe** (`observe(project_id)`). Loads from PostgreSQL:
   - all `Claim` rows for the project, plus each claim's **latest** verdict
     (ordered by `Verification.created_at`);
   - conflict pairs from `Conflict`/`ConflictClaim` where
     `kind == "value_disagreement"` (grouped into `frozenset`s of ≥2 members);
   - stale sources from `Source.freshness` in
     `{POTENTIALLY_STALE, CONTRADICTED_BY_NEWER_EVIDENCE}`;
   - `visible_evidence_sources` (default index) and `all_evidence_sources`
     (with `include_restricted=True`) from the handover evidence index;
   - readiness requirements from the latest `ReadinessEvaluation`;
   - handover statements from the latest `HandoverVersion` (only non-removed
     sections; each statement's `unsupported` flag and whether its type is
     `established_fact`).
   - A claim is "approved" when `status == ClaimStatus.VERIFIED`.

2. **Compute** — `compute_all(observations, GROUND_TRUTH)` returns the full
   report body keyed by metric name plus `dataset_version`.

3. **Assemble `metrics`** — the `value` of every `HEADLINE_METRICS` and
   `INVERTED_METRICS` key, plus `H_permission_leakage.value` and
   `permission_leakage_passed` (the boolean gate).

4. **Failures** — any metric returning `undefined: True` is recorded as
   `{"metric": name, "reason": "no data to evaluate (denominator was zero)"}`.
   If the permission-leakage check does not pass, an entry is added with the
   failing checks.

5. **Persist an `EvaluationRun`** and record an audit event
   (`evaluation_metrics_run`).

### What is stored on `EvaluationRun`

Model: [`phase5.py`](../backend/app/models/phase5.py), table
`evaluation_runs`.

| Field | Content |
| --- | --- |
| `project_id` | project the run belongs to (nullable) |
| `kind` | `EvaluationKind` (`metrics` or `successor_exercise`) |
| `dataset_version` | e.g. `continuum-ground-truth-v1` |
| `model_version` | optional, supplied by the caller |
| `configuration` | `{"evaluation_framework": "continuum-eval-v1", "observations": {claims, conflict_pairs, stale_sources, handover_statements}}` |
| `metrics` | the A–I values + `H_permission_leakage` + `permission_leakage_passed` |
| `failures` | undefined-metric and permission-leakage entries |
| `report` | the full `compute_all` body (per-metric counts, mismatches, etc.) |
| `created_by_id` | user who ran it |
| `created_at` | timestamp |

### Reproducibility guarantees

- The metric functions are pure and deterministic (no model calls, no DB
  access).
- Verification verdicts are reduced to the **latest** verdict per claim via a
  stable ordering.
- Repeated runs on **unchanged** data produce identical `metrics` and `report`.
  The integration test asserts two back-to-back runs compare with
  `regression_count == 0` and `improvement_count == 0`.

---

## 5. Comparing runs / regression detection

`EvaluationService.compare(project_id, base_run_id, candidate_run_id)`:

- Rejects runs of **different kinds** (`incomparable_runs`).
- Rejects runs with **different `dataset_version`** (`dataset_version_mismatch`)
  — differing dataset versions are not comparable.
- Computes a `delta = round(after - before, 4)` for every metric name present in
  either run.

**Tolerance.** `REGRESSION_TOLERANCE = 0.0001`. A movement whose magnitude is at
or below the tolerance is treated as noise.

**Classification:**

- For normal metrics: `delta < -tol` → regression; `delta > +tol` → improvement.
- For `INVERTED_METRICS` (e.g. `G_unsupported_handover_rate`): the sense flips —
  `delta > +tol` → regression; `delta < -tol` → improvement.

The response returns `deltas`, `regressions`, `improvements`,
`regression_count` and `improvement_count`, along with
`base_run_id`/`candidate_run_id`/`dataset_version`.

---

## 6. The successor readiness exercise (§10)

`ContinuityService.run_successor_exercise` in
[`continuity_service.py`](../backend/app/services/continuity_service.py), stamped
with `EXERCISE_DATASET_VERSION = "successor-exercise-v1"`.

It is an additional, **limited** quality check: it answers a fixed,
project-specific question set from the approved knowledge and reports which
questions the handover can and cannot answer.

### The 8 deterministic questions

| # | question_id | prompt | supporting approved claims |
| --- | --- | --- | --- |
| 1 | `locate_repository` | Locate the main application repository. | any connected GitHub source type (completed directly); else `dependency` claims containing repository keywords |
| 2 | `identify_external_service` | Identify an external service the project depends on. | `dependency` claims matching service/api/external/third-party/stripe/payment/gemini/supabase |
| 3 | `find_retry_policy` | Find the documented retry policy. | `technical_constraint`/`operational_procedure`/`dependency` claims matching retry/retries/backoff/back-off |
| 4 | `identify_deployment_blocker` | Identify an unresolved deployment blocker. | `risk`/`unfinished_work`/`task` claims matching deploy/deployment/release/rollout |
| 5 | `locate_rollback_procedure` | Locate the rollback procedure. | `operational_procedure`/`risk` claims matching rollback/roll back/revert/restore/back out/backout |
| 6 | `identify_owner` | Identify who owns or is responsible for a critical part of the project. | `ownership`/`responsibility` claims |
| 7 | `describe_current_status` | Describe the project's current status. | `status`/`process` claims |
| 8 | `find_open_question` | Find an unresolved question the successor should answer. | `open_question` claims |

### How completion is decided (deterministic)

For each question the supporting approved claims are collected. `_answer`
returns one of three outcomes:

- **`missing_information`** — no supporting claims exist. `answer = None`,
  `supporting_claim_ids = []`.
- **`blocked`** — at least one supporting claim is part of an **unresolved
  conflict** (`claim.id in conflicted`). Its knowledge cannot be relied on yet.
  `answer = None`, with the supporting claim ids and an explanation.
- **`completed`** — otherwise. `answer` = the first supporting claim's text;
  `supporting_claim_ids` = sorted ids; explanation states how many approved
  claims answered it.

`_q_repository` is a special case: if any GitHub source type is connected it
completes immediately (`"Repository sources are connected (...)"`) with no
claim ids.

### What is reported

Persisted as an `EvaluationRun` with `kind = successor_exercise`:

- `metrics`: `tasks_attempted`, `tasks_completed`, `tasks_blocked`,
  `tasks_missing_information`, and `exercise_score = 100 * completed / attempted`
  (0.0 when nothing was attempted).
- `failures`: one entry per question whose outcome is not `completed`
  (`{question_id, reason}`).
- `report`:
  - `dataset_version` = `successor-exercise-v1`,
  - `disclaimer` — the explicit caveat below,
  - `questions` — the per-question results (id, prompt, outcome, answer,
    supporting claim ids, explanation).
- `configuration` = `{"approved_claims": <count>}`.

### Explicit caveat

The exercise is **not** a simulation of human competence. The report embeds this
disclaimer verbatim:

> "This is a deterministic evidence check over approved knowledge. It does not
> simulate human competence and is not a substitute for real successor testing."

---

## 7. Running an evaluation and reading the results

All endpoints live in
[`readiness.py`](../backend/app/api/v1/readiness.py). Access roles are enforced
per endpoint via `resolve_project_access` / `resolve_workspace_access`.

| Method | Path | Role | Purpose |
| --- | --- | --- | --- |
| `POST` | `/api/v1/workspaces/{workspace_id}/evaluation/synthetic-project` | ADMIN | Seed the synthetic ground-truth project's source corpus |
| `POST` | `/api/v1/projects/{project_id}/evaluation/runs` | ADMIN | Run the reproducible evaluation and persist the result |
| `GET` | `/api/v1/projects/{project_id}/evaluation/runs` | VIEWER | List runs (newest first; `kind`, `page`, `page_size` query params) |
| `GET` | `/api/v1/projects/{project_id}/evaluation/runs/{run_id}` | VIEWER | One run, with its full report |
| `GET` | `/api/v1/projects/{project_id}/evaluation/compare?base=&candidate=` | VIEWER | Compare two runs to detect regressions |
| `POST` | `/api/v1/projects/{project_id}/successor-exercise` | MEMBER | Run the deterministic successor readiness exercise |
| `GET` | `/api/v1/projects/{project_id}/successor-exercise` | VIEWER | The most recent successor exercise |

Typical flow:

1. `POST .../evaluation/synthetic-project` to seed the corpus.
2. Run the reconstruction pipeline so real claims/evidence exist.
3. `POST .../evaluation/runs` to score against the ground truth.
4. `GET .../evaluation/runs/{run_id}` and read `metrics`, `failures` and
   `report`.
5. `POST .../successor-exercise` and read `report.questions`.

### Running the tests

From the `backend/` directory:

```powershell
pytest tests/test_phase5_evaluation.py
```

The suite covers:

- Unit tests for each pure metric (precision/recall/F1, evidence accuracy,
  conflict detection, stale recall, critical coverage, permission leakage,
  unsupported handover rate) with hand-built data.
- `test_zero_over_zero_is_reported_as_undefined` — a 0/0 returns `value == 0.0`
  and `undefined is True`.
- Integration tests over the real router: multiple runs compare with zero
  regressions/improvements on unchanged data; the successor exercise reports
  `tasks_attempted == 8`.

---

## 8. Limitations & assumptions

- **Metrics depend on the live extraction pipeline.** The ground truth is only
  a yardstick. If extraction, verification, conflict detection or staleness
  classification is weak, the metrics will be low — that is the intended signal,
  not a defect in the evaluation.
- **One synthetic dataset.** The framework ships a single ground-truth scenario
  ("Payments Service Handover"). Numbers are specific to that dataset and its
  version; runs across different `dataset_version`s are explicitly not
  comparable.
- **Keyword-based matching.** Claims are matched by claim type plus keyword
  presence, not exact text. This tolerates wording differences but is
  approximate: a claim could match on a substring without fully capturing the
  fact.
- **Zero-denominator handling.** When there is nothing to evaluate, the metric
  is `0.0` with `undefined: True` and is surfaced in `failures`. Such values must
  not be read as "scored zero" — read `undefined` / `failures` alongside.
- **Observation completeness.** Metrics that need downstream artefacts (verdicts,
  conflicts, a handover version, a readiness evaluation) will be `undefined`
  until those exist for the project. `observe` reads only the latest verdict,
  conflict set, handover version and readiness evaluation.
- **`E_stale_detection.value` is recall, not precision.** The result also carries
  `precision`, but `value` is definitionally the recall.
- **The successor exercise is a limited check.** It answers a fixed set of 8
  project-specific questions deterministically from approved knowledge. It does
  **not** simulate human competence and is **not** a substitute for real
  successor testing (see the embedded disclaimer).
- **`G_unsupported_handover_rate` is inverted.** Lower is better; the comparison
  logic flips its sense accordingly, so it must not be read like the headline
  metrics.
- **Exercise scoring is a simple ratio.** `exercise_score` counts completed
  questions over attempted questions; it does not weight question difficulty or
  importance.
