from app.evaluation.evidence_scenarios import EVIDENCE_SCENARIOS
from app.services.evidence_quality import assess_evidence_quality


def test_synthetic_evidence_scenarios_match_declared_qualitative_ground_truth():
    for scenario in EVIDENCE_SCENARIOS:
        result = assess_evidence_quality(
            statement=scenario.statement,
            evidence_level=scenario.evidence_level,
            evidence=list(scenario.evidence),
            contradicting_evidence=list(scenario.contradicting_evidence),
            freshness_status=scenario.freshness_status,
        )
        assert result["status"] == scenario.expected_status, scenario.name
        assert result["methodology"] == "qualitative-rules-v1; no aggregate score or probability"
        assert result["verification_status"] == "unverified"
        assert result["last_verification_at"] is None


def test_evidence_assessment_explains_each_dimension_without_probability():
    result = assess_evidence_quality(
        statement="The API listens on port 8080",
        evidence_level="observed",
        evidence=[{
            "source_id": "source-1",
            "source_type": "github_file",
            "file_path": "src/app.py",
            "source_location": "src/app.py:4",
            "quote": "The API listens on port 8080",
            "current_validity": "current_snapshot",
        }],
    )
    assert result["status"] == "supported"
    assert set(result["dimensions"]) == {
        "source_reliability", "directness", "recency", "corroboration", "consistency", "completeness"
    }
    assert all(dimension["reason"] for dimension in result["dimensions"].values())
    assert "score" not in result and "probability" not in result


def test_activity_evidence_does_not_prove_current_repository_behavior():
    result = assess_evidence_quality(
        statement="Current code uses the commit's behavior",
        evidence_level="observed",
        evidence=[{
            "source_id": "commit-1", "source_type": "github_commit",
            "quote": "Changed deployment configuration", "current_validity": "not_rechecked",
        }],
    )
    assert result["dimensions"]["source_reliability"]["status"] == "recorded_activity"
    assert result["status"] == "provisional"
