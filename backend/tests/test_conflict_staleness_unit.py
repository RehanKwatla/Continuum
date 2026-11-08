"""Deterministic conflict- and staleness-detection unit tests.

Both detectors are pure application code, so these tests run without a database
and without a model. They pin the specification's guard rails:

* not every differing statement is a conflict;
* an ownership change over time is informational, not a contradiction;
* a source being old does not, by itself, make it stale.
"""

from __future__ import annotations

import uuid

from app.ai.contracts import ConflictFinding, ExtractedClaim, SourceContext
from app.models.enums import ClaimType, FreshnessStatus
from app.services.claim_validation import claim_dedup_key
from app.services.conflict_detector import ConflictDetector
from app.services.staleness_service import StalenessDetector

from synthetic_project import utc


def make_claim(
    text: str,
    claim_type: ClaimType,
    entity: str | None,
    *,
    when=None,
    source_ids: list[uuid.UUID] | None = None,
) -> ExtractedClaim:
    return ExtractedClaim(
        project_id=uuid.uuid4(),
        text=text,
        claim_type=claim_type,
        entity=entity,
        dedup_key=claim_dedup_key(claim_type, text, entity),
        time_context=when,
        source_ids=source_ids or [uuid.uuid4()],
    )


def make_source(
    source_type: str,
    name: str,
    when,
    metadata: dict | None = None,
) -> SourceContext:
    return SourceContext(
        source_id=uuid.uuid4(),
        source_name=name,
        source_type=source_type,
        source_date=when,
        metadata=metadata or {},
    )


# ---------------------------------------------------------------------------
# Conflict detection
# ---------------------------------------------------------------------------
def test_same_property_with_different_values_is_a_conflict() -> None:
    left = make_claim(
        "The production database is PostgreSQL 13.",
        ClaimType.TECHNICAL_CONSTRAINT,
        "database",
    )
    right = make_claim(
        "The production database is PostgreSQL 15.",
        ClaimType.TECHNICAL_CONSTRAINT,
        "database",
    )
    findings = ConflictDetector().detect([left, right])
    assert len(findings) == 1
    assert findings[0].kind == "value_disagreement"
    assert set(findings[0].claim_local_ids) == {left.local_id, right.local_id}


def test_different_properties_are_not_a_conflict() -> None:
    retries = make_claim(
        "Webhook retries are capped at three attempts.",
        ClaimType.TECHNICAL_CONSTRAINT,
        "payment_webhook",
    )
    timeout = make_claim(
        "Webhook timeout is 30 seconds.",
        ClaimType.TECHNICAL_CONSTRAINT,
        "payment_webhook",
    )
    # Same entity and category, but two different properties: not a conflict.
    assert ConflictDetector().detect([retries, timeout]) == []


def test_ownership_change_over_time_is_informational_not_a_conflict() -> None:
    alice = make_claim(
        "The payments module is owned by Alice.",
        ClaimType.OWNERSHIP,
        "payments",
        when=utc(2024, 2, 10),
    )
    bob = make_claim(
        "The payments module is owned by Bob.",
        ClaimType.OWNERSHIP,
        "payments",
        when=utc(2024, 6, 1),
    )
    findings = ConflictDetector().detect([alice, bob])
    assert len(findings) == 1
    assert findings[0].kind == "changed_over_time"


def test_ownership_within_the_same_window_is_a_conflict() -> None:
    alice = make_claim(
        "The payments module is owned by Alice.",
        ClaimType.OWNERSHIP,
        "payments",
        when=utc(2024, 2, 10),
    )
    bob = make_claim(
        "The payments module is owned by Bob.",
        ClaimType.OWNERSHIP,
        "payments",
        when=utc(2024, 2, 15),
    )
    findings = ConflictDetector().detect([alice, bob])
    assert len(findings) == 1
    assert findings[0].kind == "value_disagreement"


def test_the_same_owner_stated_twice_is_not_a_conflict() -> None:
    first = make_claim(
        "The payments module is owned by Alice.",
        ClaimType.OWNERSHIP,
        "payments",
    )
    second = make_claim(
        "Ownership of payments sits with Alice.",
        ClaimType.OWNERSHIP,
        "payments",
    )
    assert ConflictDetector().detect([first, second]) == []


# ---------------------------------------------------------------------------
# Staleness detection
# ---------------------------------------------------------------------------
def test_document_superseded_by_a_newer_change_is_potentially_stale() -> None:
    readme = make_source(
        "github_readme", "README.md", utc(2024, 1, 5), {"readme_path": "README.md"}
    )
    commit = make_source(
        "github_commit",
        "commit abc1234",
        utc(2024, 6, 1),
        {"changed_files": ["README.md", "scripts/release.sh"]},
    )
    warnings = StalenessDetector().detect(sources=[readme, commit], claims=[], conflicts=[])
    flagged = {warning.source_id: warning for warning in warnings}
    assert readme.source_id in flagged
    assert flagged[readme.source_id].status is FreshnessStatus.POTENTIALLY_STALE
    assert flagged[readme.source_id].related_source_id == commit.source_id


def test_a_merely_old_source_is_not_stale() -> None:
    old_readme = make_source(
        "github_readme", "README.md", utc(2019, 1, 1), {"readme_path": "README.md"}
    )
    # Nothing newer exists: age alone must not raise a staleness flag.
    assert (
        StalenessDetector().detect(sources=[old_readme], claims=[], conflicts=[]) == []
    )


def test_a_change_to_an_unrelated_file_does_not_stale_the_document() -> None:
    readme = make_source(
        "github_readme", "README.md", utc(2024, 1, 5), {"readme_path": "README.md"}
    )
    commit = make_source(
        "github_commit",
        "commit abc1234",
        utc(2024, 6, 1),
        {"changed_files": ["scripts/release.sh"]},
    )
    assert (
        StalenessDetector().detect(sources=[readme, commit], claims=[], conflicts=[]) == []
    )


def test_newer_contradiction_marks_the_older_source() -> None:
    older_source = make_source(
        "uploaded_markdown", "architecture-notes.md", utc(2024, 2, 10)
    )
    newer_source = make_source("github_commit", "commit abc1234", utc(2024, 6, 1))
    older_claim = make_claim(
        "The production database is PostgreSQL 13.",
        ClaimType.TECHNICAL_CONSTRAINT,
        "database",
        when=utc(2024, 2, 10),
        source_ids=[older_source.source_id],
    )
    newer_claim = make_claim(
        "The production database is PostgreSQL 15.",
        ClaimType.TECHNICAL_CONSTRAINT,
        "database",
        when=utc(2024, 6, 1),
        source_ids=[newer_source.source_id],
    )
    conflict = ConflictFinding(
        kind="value_disagreement",
        property_key="database · postgresql",
        claim_local_ids=[older_claim.local_id, newer_claim.local_id],
    )
    warnings = StalenessDetector().detect(
        sources=[older_source, newer_source],
        claims=[older_claim, newer_claim],
        conflicts=[conflict],
    )
    flagged = {warning.source_id: warning for warning in warnings}
    assert flagged[older_source.source_id].status is (
        FreshnessStatus.CONTRADICTED_BY_NEWER_EVIDENCE
    )
    # The newer source is not stale.
    assert newer_source.source_id not in flagged


def test_contradicted_outranks_potentially_stale() -> None:
    readme = make_source(
        "github_readme", "README.md", utc(2024, 1, 5), {"readme_path": "README.md"}
    )
    commit = make_source(
        "github_commit",
        "commit abc1234",
        utc(2024, 6, 1),
        {"changed_files": ["README.md"]},
    )
    readme_claim = make_claim(
        "The README deploy steps use PostgreSQL 13.",
        ClaimType.TECHNICAL_CONSTRAINT,
        "database",
        when=utc(2024, 1, 5),
        source_ids=[readme.source_id],
    )
    commit_claim = make_claim(
        "The README deploy steps use PostgreSQL 15.",
        ClaimType.TECHNICAL_CONSTRAINT,
        "database",
        when=utc(2024, 6, 1),
        source_ids=[commit.source_id],
    )
    conflict = ConflictFinding(
        kind="value_disagreement",
        property_key="database · postgresql",
        claim_local_ids=[readme_claim.local_id, commit_claim.local_id],
    )
    warnings = StalenessDetector().detect(
        sources=[readme, commit],
        claims=[readme_claim, commit_claim],
        conflicts=[conflict],
    )
    flagged = {warning.source_id: warning for warning in warnings}
    # Rule 1 flagged it potentially-stale; rule 2 must upgrade, not be masked.
    assert flagged[readme.source_id].status is (
        FreshnessStatus.CONTRADICTED_BY_NEWER_EVIDENCE
    )
