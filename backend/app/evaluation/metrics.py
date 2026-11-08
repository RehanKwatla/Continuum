"""Pure evaluation metrics (Phase 5 §9).

Every function here is a pure function of already-loaded data: it takes the
observations read from PostgreSQL and the ground-truth dataset and returns a
result dictionary with a ``value`` plus the counts that produced it. No function
reads the database, calls a model or invents a number.

Definitions (all ratios are ``0.0`` when their denominator is zero, and every
result carries ``undefined: True`` in that case, so a "0/0" is never silently
presented as a real score):

* ``precision = tp / (tp + fp)``
* ``recall = tp / (tp + fn)``
* ``f1 = 2 * precision * recall / (precision + recall)``
* ``accuracy = correct / evaluated``

A ground-truth claim is **matched** when an observed claim has the same claim
type *and* contains at least one of the ground-truth claim's keywords. Keywords
(not exact text) are used on purpose: extraction is allowed to phrase a fact
differently, and the evaluation measures whether the *fact* was captured.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.evaluation.ground_truth import GroundTruthClaim, GroundTruthDataset


def _ratio(numerator: int, denominator: int) -> tuple[float, bool]:
    if denominator <= 0:
        return 0.0, True
    return round(numerator / denominator, 4), False


# ---------------------------------------------------------------------------
# Observations (built by the service from real database rows)
# ---------------------------------------------------------------------------
@dataclass
class ClaimObservation:
    """One claim as it exists in the database, with its evidence and verdict."""

    id: str
    text: str
    claim_type: str
    entity: str | None
    status: str
    approved: bool
    critical: bool
    evidence_sources: list[str] = field(default_factory=list)
    verdict: str | None = None


@dataclass
class Observations:
    """Everything the metrics need, loaded once from the database."""

    claims: list[ClaimObservation] = field(default_factory=list)
    #: Observed contradictions as ``frozenset({claim_id, claim_id})``.
    conflict_pairs: list[frozenset[str]] = field(default_factory=list)
    #: Source names a staleness check flagged.
    stale_sources: list[str] = field(default_factory=list)
    #: Evidence source names visible without restricted material.
    visible_evidence_sources: list[str] = field(default_factory=list)
    #: Evidence source names visible when restricted material is included.
    all_evidence_sources: list[str] = field(default_factory=list)
    #: ``{requirement_id: completion}`` from the latest readiness evaluation.
    readiness_requirements: dict[str, str] = field(default_factory=dict)
    #: Handover statements: ``{"unsupported": bool, "evidence_backed": bool}``.
    handover_statements: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------
def _matches(expected: GroundTruthClaim, observed: ClaimObservation) -> bool:
    if observed.claim_type != expected.claim_type.value:
        return False
    haystack = f"{observed.text} {observed.entity or ''}".casefold()
    return any(keyword.casefold() in haystack for keyword in expected.keywords)


def match_claims(
    observations: list[ClaimObservation], dataset: GroundTruthDataset
) -> dict[str, ClaimObservation]:
    """Return ``{ground_truth_key: observed claim}`` for every matched fact."""
    matched: dict[str, ClaimObservation] = {}
    claimed: set[str] = set()
    for expected in dataset.claims:
        for observed in observations:
            if observed.id in claimed:
                continue
            if _matches(expected, observed):
                matched[expected.key] = observed
                claimed.add(observed.id)
                break
    return matched


# ---------------------------------------------------------------------------
# A. Claim extraction precision and recall
# ---------------------------------------------------------------------------
def claim_extraction(
    observations: list[ClaimObservation], dataset: GroundTruthDataset
) -> dict[str, Any]:
    matched = match_claims(observations, dataset)
    matched_ids = {item.id for item in matched.values()}
    tp = len(matched)
    fn = len(dataset.claims) - tp
    fp = sum(1 for item in observations if item.id not in matched_ids)
    precision, p_undefined = _ratio(tp, tp + fp)
    recall, r_undefined = _ratio(tp, tp + fn)
    f1, _ = _ratio(2 * tp, 2 * tp + fp + fn)
    return {
        "value": precision,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "expected_total": len(dataset.claims),
        "observed_total": len(observations),
        "undefined": p_undefined and r_undefined,
        "matched": {key: item.id for key, item in matched.items()},
        "missed": [
            expected.key for expected in dataset.claims if expected.key not in matched
        ],
    }


# ---------------------------------------------------------------------------
# B. Evidence citation accuracy
# ---------------------------------------------------------------------------
def evidence_accuracy(
    observations: list[ClaimObservation], dataset: GroundTruthDataset
) -> dict[str, Any]:
    """Does the cited source actually support the claim?"""
    matched = match_claims(observations, dataset)
    evaluated = 0
    correct = 0
    wrong: list[dict[str, Any]] = []
    for key, observed in matched.items():
        expected = dataset.claim(key)
        evaluated += 1
        if expected.evidence_source in observed.evidence_sources:
            correct += 1
        else:
            wrong.append(
                {
                    "ground_truth_key": key,
                    "expected_source": expected.evidence_source,
                    "cited_sources": list(observed.evidence_sources),
                }
            )
    value, undefined = _ratio(correct, evaluated)
    return {
        "value": value,
        "correct": correct,
        "evaluated": evaluated,
        "incorrect": wrong,
        "undefined": undefined,
    }


# ---------------------------------------------------------------------------
# C. Verification accuracy
# ---------------------------------------------------------------------------
def verification_accuracy(
    observations: list[ClaimObservation], dataset: GroundTruthDataset
) -> dict[str, Any]:
    """Does the verifier reach the right verdict for each matched claim?"""
    matched = match_claims(observations, dataset)
    evaluated = 0
    correct = 0
    confused: list[dict[str, Any]] = []
    for key, observed in matched.items():
        if observed.verdict is None:
            continue
        expected = dataset.claim(key)
        evaluated += 1
        if observed.verdict == expected.expected_verdict:
            correct += 1
        else:
            confused.append(
                {
                    "ground_truth_key": key,
                    "expected": expected.expected_verdict,
                    "actual": observed.verdict,
                }
            )
    value, undefined = _ratio(correct, evaluated)
    return {
        "value": value,
        "correct": correct,
        "evaluated": evaluated,
        "mismatches": confused,
        "undefined": undefined,
    }


# ---------------------------------------------------------------------------
# D. Conflict detection precision and recall
# ---------------------------------------------------------------------------
def conflict_detection(
    observations: Observations, dataset: GroundTruthDataset
) -> dict[str, Any]:
    matched = match_claims(observations.claims, dataset)
    expected_pairs: set[frozenset[str]] = set()
    for conflict in dataset.conflicts:
        left = matched.get(conflict.left)
        right = matched.get(conflict.right)
        if left is not None and right is not None:
            expected_pairs.add(frozenset({left.id, right.id}))
    observed_pairs = {pair for pair in observations.conflict_pairs if len(pair) == 2}
    tp = len(expected_pairs & observed_pairs)
    fp = len(observed_pairs - expected_pairs)
    fn = len(expected_pairs - observed_pairs)
    precision, p_undef = _ratio(tp, tp + fp)
    recall, r_undef = _ratio(tp, tp + fn)
    return {
        "value": precision,
        "precision": precision,
        "recall": recall,
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "expected_total": len(expected_pairs),
        "observed_total": len(observed_pairs),
        "undefined": p_undef and r_undef,
    }


# ---------------------------------------------------------------------------
# E. Stale-information detection quality
# ---------------------------------------------------------------------------
def stale_detection(
    observations: Observations, dataset: GroundTruthDataset
) -> dict[str, Any]:
    expected = set(dataset.stale_sources)
    observed = set(observations.stale_sources)
    tp = len(expected & observed)
    fp = len(observed - expected)
    fn = len(expected - observed)
    precision, p_undef = _ratio(tp, tp + fp)
    recall, r_undef = _ratio(tp, tp + fn)
    return {
        "value": recall,
        "precision": precision,
        "recall": recall,
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "expected_total": len(expected),
        "observed_total": len(observed),
        "undefined": p_undef and r_undef,
    }


# ---------------------------------------------------------------------------
# F. Critical knowledge coverage
# ---------------------------------------------------------------------------
def critical_knowledge_coverage(
    observations: list[ClaimObservation], dataset: GroundTruthDataset
) -> dict[str, Any]:
    critical = [item for item in dataset.claims if item.critical]
    matched = match_claims(observations, dataset)
    present = 0
    approved = 0
    for expected in critical:
        observed = matched.get(expected.key)
        if observed is not None:
            present += 1
            if observed.approved:
                approved += 1
    present_ratio, present_undefined = _ratio(present, len(critical))
    approved_ratio, approved_undefined = _ratio(approved, len(critical))
    return {
        "value": approved_ratio,
        "present_coverage": present_ratio,
        "approved_coverage": approved_ratio,
        "critical_total": len(critical),
        "present": present,
        "approved": approved,
        "undefined": present_undefined and approved_undefined,
    }


# ---------------------------------------------------------------------------
# G. Unsupported handover statement rate
# ---------------------------------------------------------------------------
def unsupported_handover_rate(observations: Observations) -> dict[str, Any]:
    evidence_backed = [
        item for item in observations.handover_statements if item.get("evidence_backed")
    ]
    unsupported = [item for item in evidence_backed if item.get("unsupported")]
    rate, undefined = _ratio(len(unsupported), len(evidence_backed))
    return {
        "value": rate,
        "unsupported": len(unsupported),
        "evidence_backed_statements": len(evidence_backed),
        "total_statements": len(observations.handover_statements),
        "undefined": undefined,
    }


# ---------------------------------------------------------------------------
# H. Permission leakage check
# ---------------------------------------------------------------------------
def permission_leakage_check(
    observations: Observations, dataset: GroundTruthDataset
) -> dict[str, Any]:
    """A restricted source must be hidden by default and present when allowed."""
    restricted = dataset.restricted_source
    if restricted is None:
        return {"value": 1.0, "passed": True, "checks": [], "undefined": True}
    visible = set(observations.visible_evidence_sources)
    everything = set(observations.all_evidence_sources)
    checks = [
        {
            "check": "restricted_source_hidden_by_default",
            "passed": restricted not in visible,
            "detail": f"'{restricted}' must not appear in the default evidence index.",
        },
        {
            "check": "restricted_source_present_with_explicit_access",
            "passed": restricted in everything,
            "detail": f"'{restricted}' must appear when restricted access is explicit.",
        },
    ]
    passed = all(item["passed"] for item in checks)
    return {"value": 1.0 if passed else 0.0, "passed": passed, "checks": checks, "undefined": False}


# ---------------------------------------------------------------------------
# I. Handover readiness agreement against human-labelled requirements
# ---------------------------------------------------------------------------
def readiness_agreement(observations: Observations, dataset: GroundTruthDataset) -> dict[str, Any]:
    expectations = dataset.readiness_expectations
    if not expectations:
        return {"value": 0.0, "agree": 0, "evaluated": 0, "disagreements": [], "undefined": True}
    agree = 0
    disagreements: list[dict[str, Any]] = []
    for requirement_id, expected in expectations.items():
        actual = observations.readiness_requirements.get(requirement_id)
        if actual == expected.value:
            agree += 1
        else:
            disagreements.append(
                {
                    "requirement_id": requirement_id,
                    "expected": expected.value,
                    "actual": actual,
                }
            )
    value, undefined = _ratio(agree, len(expectations))
    return {
        "value": value,
        "agree": agree,
        "evaluated": len(expectations),
        "disagreements": disagreements,
        "undefined": undefined,
    }


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------
def compute_all(observations: Observations, dataset: GroundTruthDataset) -> dict[str, Any]:
    """Run every metric and return the full, reproducible result body."""
    return {
        "dataset_version": dataset.version,
        "A_claim_extraction": claim_extraction(observations.claims, dataset),
        "B_evidence_accuracy": evidence_accuracy(observations.claims, dataset),
        "C_verification_accuracy": verification_accuracy(observations.claims, dataset),
        "D_conflict_detection": conflict_detection(observations, dataset),
        "E_stale_detection": stale_detection(observations, dataset),
        "F_critical_knowledge_coverage": critical_knowledge_coverage(observations.claims, dataset),
        "G_unsupported_handover_rate": unsupported_handover_rate(observations),
        "H_permission_leakage": permission_leakage_check(observations, dataset),
        "I_readiness_agreement": readiness_agreement(observations, dataset),
    }


#: Metrics that are percentages in ``[0, 1]`` and where higher is better.
HEADLINE_METRICS: tuple[str, ...] = (
    "A_claim_extraction",
    "B_evidence_accuracy",
    "C_verification_accuracy",
    "D_conflict_detection",
    "E_stale_detection",
    "F_critical_knowledge_coverage",
    "I_readiness_agreement",
)

#: Metrics where *lower* is better.
INVERTED_METRICS: tuple[str, ...] = ("G_unsupported_handover_rate",)


__all__ = [
    "HEADLINE_METRICS",
    "INVERTED_METRICS",
    "ClaimObservation",
    "Observations",
    "claim_extraction",
    "compute_all",
    "conflict_detection",
    "critical_knowledge_coverage",
    "evidence_accuracy",
    "match_claims",
    "permission_leakage_check",
    "readiness_agreement",
    "stale_detection",
    "unsupported_handover_rate",
    "verification_accuracy",
]
