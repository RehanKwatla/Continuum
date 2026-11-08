"""Phase 3 AI contract tests: the claim / verification schemas.

These assert the governance rule that no automated agent may verify a claim.
"""

from __future__ import annotations

import uuid

import pytest

from app.models.enums import ClaimStatus, ClaimType, VerificationVerdict
from app.schemas.claim import (
    AI_ASSIGNABLE_STATUSES,
    HUMAN_ONLY_STATUSES,
    Claim,
    ClaimExtractionResult,
    Verification,
    assert_ai_assignable_status,
)


def test_verified_status_is_human_only() -> None:
    assert HUMAN_ONLY_STATUSES == {ClaimStatus.VERIFIED}
    assert ClaimStatus.VERIFIED not in AI_ASSIGNABLE_STATUSES
    assert AI_ASSIGNABLE_STATUSES == {
        ClaimStatus.SUPPORTED,
        ClaimStatus.UNCERTAIN,
        ClaimStatus.CONFLICT,
    }


def test_agent_cannot_assign_verified_status() -> None:
    with pytest.raises(ValueError):
        assert_ai_assignable_status(ClaimStatus.VERIFIED)
    # Agent-assignable statuses pass.
    assert_ai_assignable_status(ClaimStatus.SUPPORTED)
    assert_ai_assignable_status(ClaimStatus.UNCERTAIN)
    assert_ai_assignable_status(ClaimStatus.CONFLICT)


def test_claim_defaults_are_conservative() -> None:
    claim = Claim(id=uuid.uuid4(), text="The billing service owns invoices.")
    assert claim.status is ClaimStatus.UNCERTAIN
    assert claim.claim_type is ClaimType.OTHER
    assert claim.critical is False
    assert claim.source_span_ids == []


def test_verification_verdict_enum_values() -> None:
    assert {verdict.value for verdict in VerificationVerdict} == {"supports", "partly", "none"}
    verification = Verification(claim_id=uuid.uuid4(), verdict=VerificationVerdict.SUPPORTS)
    assert verification.contradicted_by == []


def test_extraction_result_contract() -> None:
    result = ClaimExtractionResult(project_id=uuid.uuid4(), model_name="gemini-2.0-flash")
    assert result.claims == []
