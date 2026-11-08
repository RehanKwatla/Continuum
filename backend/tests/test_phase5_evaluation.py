"""Phase 5 evaluation framework tests (§9–§10).

The metric functions are pure, so they are tested directly with a tiny
hand-built ground-truth dataset and hand-built observations — the exact data
shapes the service loads from PostgreSQL. The integration tests then drive the
real router: run metrics, list and compare runs, run the successor exercise and
read the continuity scorecard and system health over a real database.
"""

from __future__ import annotations

from app.evaluation.ground_truth import (
    GROUND_TRUTH_VERSION,
    GroundTruthClaim,
    GroundTruthConflict,
    GroundTruthDataset,
)
from app.evaluation.metrics import (
    HEADLINE_METRICS,
    ClaimObservation,
    Observations,
    claim_extraction,
    conflict_detection,
    critical_knowledge_coverage,
    evidence_accuracy,
    permission_leakage_check,
    stale_detection,
    unsupported_handover_rate,
)
from app.models.enums import ClaimType
from app.services.continuity_service import EXERCISE_DATASET_VERSION


# ---------------------------------------------------------------------------
# Unit: hand-built dataset + observations
# ---------------------------------------------------------------------------
def _mini_dataset() -> GroundTruthDataset:
    return GroundTruthDataset(
        version="mini-v1",
        project_name="Mini",
        claims=(
            GroundTruthClaim(
                key="alpha",
                text="The cache is Redis.",
                claim_type=ClaimType.TECHNICAL_CONSTRAINT,
                entity="cache",
                keywords=("redis",),
                evidence_source="notes.md",
                critical=True,
            ),
            GroundTruthClaim(
                key="beta",
                text="The queue is SQS.",
                claim_type=ClaimType.TECHNICAL_CONSTRAINT,
                entity="queue",
                keywords=("sqs",),
                evidence_source="design.md",
                critical=True,
            ),
        ),
        conflicts=(
            GroundTruthConflict(left="alpha", right="beta", property_key="cache"),
        ),
        stale_sources=("README.md",),
        restricted_source="secret.md",
        missing_knowledge=(),
        readiness_expectations={},
    )


def _obs_alpha() -> ClaimObservation:
    return ClaimObservation(
        id="a1",
        text="The cache is Redis in production.",
        claim_type=ClaimType.TECHNICAL_CONSTRAINT.value,
        entity="cache",
        status="Verified",
        approved=True,
        critical=True,
        evidence_sources=["notes.md"],
        verdict="supports",
    )


def _obs_extra() -> ClaimObservation:
    return ClaimObservation(
        id="x1",
        text="An unrelated note about the office coffee machine.",
        claim_type=ClaimType.STATUS.value,
        entity=None,
        status="Verified",
        approved=True,
        critical=False,
        evidence_sources=["misc.md"],
    )


def test_claim_extraction_precision_recall_and_f1() -> None:
    dataset = _mini_dataset()
    observations = [_obs_alpha(), _obs_extra()]

    result = claim_extraction(observations, dataset)

    assert result["true_positives"] == 1
    assert result["false_negatives"] == 1
    assert result["false_positives"] == 1
    assert result["precision"] == 0.5
    assert result["recall"] == 0.5
    assert result["f1"] == 0.5
    assert result["missed"] == ["beta"]
    assert result["undefined"] is False


def test_evidence_accuracy_uses_expected_source() -> None:
    dataset = _mini_dataset()

    correct = evidence_accuracy([_obs_alpha()], dataset)
    assert correct["value"] == 1.0
    assert correct["evaluated"] == 1
    assert correct["incorrect"] == []

    mismatched = ClaimObservation(
        id="a2",
        text="The cache is Redis.",
        claim_type=ClaimType.TECHNICAL_CONSTRAINT.value,
        entity="cache",
        status="Verified",
        approved=True,
        critical=True,
        evidence_sources=["wrong.md"],
    )
    wrong = evidence_accuracy([mismatched], dataset)
    assert wrong["value"] == 0.0
    assert wrong["incorrect"][0]["expected_source"] == "notes.md"


def test_conflict_detection_precision_and_recall() -> None:
    dataset = _mini_dataset()
    alpha = _obs_alpha()
    beta = ClaimObservation(
        id="b1",
        text="The queue is SQS.",
        claim_type=ClaimType.TECHNICAL_CONSTRAINT.value,
        entity="queue",
        status="Verified",
        approved=True,
        critical=True,
        evidence_sources=["design.md"],
    )

    found = Observations(claims=[alpha, beta], conflict_pairs=[frozenset({"a1", "b1"})])
    result = conflict_detection(found, dataset)
    assert result["true_positives"] == 1
    assert result["false_positives"] == 0
    assert result["false_negatives"] == 0
    assert result["precision"] == 1.0
    assert result["recall"] == 1.0

    missed = conflict_detection(Observations(claims=[alpha, beta]), dataset)
    assert missed["recall"] == 0.0
    assert missed["false_negatives"] == 1


def test_stale_detection_recall() -> None:
    dataset = _mini_dataset()

    matched = stale_detection(
        Observations(stale_sources=["README.md", "other.md"]), dataset
    )
    assert matched["true_positives"] == 1
    assert matched["false_positives"] == 1
    assert matched["recall"] == 1.0


def test_critical_knowledge_coverage_counts_approved() -> None:
    dataset = _mini_dataset()
    observations = [_obs_alpha()]

    result = critical_knowledge_coverage(observations, dataset)
    assert result["critical_total"] == 2
    assert result["present"] == 1
    assert result["approved"] == 1
    assert result["present_coverage"] == 0.5
    assert result["approved_coverage"] == 0.5


def test_permission_leakage_check_passes_and_fails() -> None:
    dataset = _mini_dataset()

    ok = permission_leakage_check(
        Observations(
            visible_evidence_sources=["notes.md"],
            all_evidence_sources=["notes.md", "secret.md"],
        ),
        dataset,
    )
    assert ok["passed"] is True
    assert ok["value"] == 1.0

    leaked = permission_leakage_check(
        Observations(
            visible_evidence_sources=["notes.md", "secret.md"],
            all_evidence_sources=["notes.md", "secret.md"],
        ),
        dataset,
    )
    assert leaked["passed"] is False
    assert leaked["value"] == 0.0


def test_unsupported_handover_rate() -> None:
    observations = Observations(
        handover_statements=[
            {"unsupported": True, "evidence_backed": True},
            {"unsupported": False, "evidence_backed": True},
            {"unsupported": True, "evidence_backed": False},
        ]
    )
    result = unsupported_handover_rate(observations)
    assert result["evidence_backed_statements"] == 2
    assert result["unsupported"] == 1
    assert result["value"] == 0.5


def test_zero_over_zero_is_reported_as_undefined() -> None:
    empty = GroundTruthDataset(
        version="empty-v1",
        project_name="Empty",
        claims=(),
        conflicts=(),
        stale_sources=(),
        restricted_source=None,
        missing_knowledge=(),
    )
    result = claim_extraction([], empty)
    assert result["value"] == 0.0
    assert result["undefined"] is True


# ---------------------------------------------------------------------------
# Integration: evaluation runs
# ---------------------------------------------------------------------------
def test_run_metrics_persists_a_reproducible_report(client, project, auth_headers) -> None:
    response = client.post(
        f"/api/v1/projects/{project['id']}/evaluation/runs",
        json={},
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    run = response.json()

    assert run["kind"] == "metrics"
    assert run["dataset_version"] == GROUND_TRUTH_VERSION
    assert set(HEADLINE_METRICS).issubset(run["metrics"])
    assert "H_permission_leakage" in run["metrics"]
    assert run["report"]["dataset_version"] == GROUND_TRUTH_VERSION
    assert "A_claim_extraction" in run["report"]


def test_list_runs_and_compare_two_runs(client, project, auth_headers) -> None:
    first = client.post(
        f"/api/v1/projects/{project['id']}/evaluation/runs", json={}, headers=auth_headers
    ).json()
    second = client.post(
        f"/api/v1/projects/{project['id']}/evaluation/runs", json={}, headers=auth_headers
    ).json()

    listed = client.get(
        f"/api/v1/projects/{project['id']}/evaluation/runs", headers=auth_headers
    )
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["total"] == 2
    assert {first["id"], second["id"]} == {item["id"] for item in body["items"]}

    compared = client.get(
        f"/api/v1/projects/{project['id']}/evaluation/compare",
        params={"base": first["id"], "candidate": second["id"]},
        headers=auth_headers,
    )
    assert compared.status_code == 200, compared.text
    comparison = compared.json()
    assert comparison["base_run_id"] == first["id"]
    assert comparison["candidate_run_id"] == second["id"]
    assert comparison["dataset_version"] == GROUND_TRUTH_VERSION
    assert comparison["deltas"]
    assert comparison["regression_count"] == 0
    assert comparison["improvement_count"] == 0


# ---------------------------------------------------------------------------
# Integration: successor exercise
# ---------------------------------------------------------------------------
def test_successor_exercise_run_and_latest(client, project, auth_headers) -> None:
    response = client.post(
        f"/api/v1/projects/{project['id']}/successor-exercise", headers=auth_headers
    )
    assert response.status_code == 201, response.text
    run = response.json()

    assert run["kind"] == "successor_exercise"
    assert run["dataset_version"] == EXERCISE_DATASET_VERSION
    assert run["metrics"]["tasks_attempted"] == 8
    assert run["metrics"]["tasks_completed"] == 0
    assert len(run["report"]["questions"]) == 8

    latest = client.get(
        f"/api/v1/projects/{project['id']}/successor-exercise", headers=auth_headers
    )
    assert latest.status_code == 200, latest.text
    assert latest.json()["id"] == run["id"]


# ---------------------------------------------------------------------------
# Integration: scorecard and system health
# ---------------------------------------------------------------------------
def test_scorecard_exposes_documented_keys(client, project, auth_headers) -> None:
    response = client.get(
        f"/api/v1/projects/{project['id']}/scorecard", headers=auth_headers
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["project_id"] == project["id"]
    assert body["handover_readiness"]["overall_score"] is None
    assert "blocker_count" in body["handover_readiness"]
    assert "open" in body["conflicts"]
    assert "total" in body["conflicts"]
    assert "open" in body["missing_knowledge"]
    assert "high_risk" in body["knowledge_dependencies"]
    assert "total" in body["successor_tasks"]
    assert "total_sources" in body["source_coverage"]
    assert body["generated_at"]


def test_system_health_reports_database_and_status(client, project, auth_headers) -> None:
    response = client.get(
        f"/api/v1/projects/{project['id']}/system-health", headers=auth_headers
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["project_id"] == project["id"]
    assert body["database"] == "ok"
    assert body["status"] == "ok"
    assert isinstance(body["sources_by_status"], dict)
    assert isinstance(body["processing_runs_by_status"], dict)
    assert isinstance(body["recent_runs"], list)
