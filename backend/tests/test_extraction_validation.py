"""Extraction and claim-validation unit tests.

These exercise the deterministic gate between the model and the database with a
*scripted* provider (see ``fake_provider``): the model is never contacted, so the
results here describe application-code behaviour, not model performance.

Categories covered: extraction, claim validation, missing evidence, citation
correctness (fabricated handles), atomicity, ownership-without-cue, duplicate
deduplication and access-label tightening.
"""

from __future__ import annotations

import uuid

from app.ai.contracts import EvidenceChunk, RawClaim, SourceContext
from app.ai.extractor import ExtractorAgent
from app.models.enums import AccessLabel, ClaimType
from app.services.claim_validation import (
    ClaimRejection,
    ClaimValidator,
    claim_dedup_key,
    strictest_access_label,
)

from fake_provider import FailingFake, FakeProvider, NonJsonFake

PROJECT_ID = uuid.uuid4()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def make_chunk(
    label: str,
    text: str,
    *,
    source_id: uuid.UUID | None = None,
    source_name: str = "architecture-notes.md",
    source_type: str = "uploaded_markdown",
) -> EvidenceChunk:
    return EvidenceChunk(
        label=label,
        span_id=uuid.uuid4(),
        source_id=source_id or uuid.uuid4(),
        source_name=source_name,
        source_type=source_type,
        location="lines 1-2",
        text=text,
    )


def validate(
    raw: RawClaim,
    chunks: list[EvidenceChunk],
    *,
    validator: ClaimValidator | None = None,
    access: dict[uuid.UUID, AccessLabel] | None = None,
) -> tuple[object, ClaimRejection | None]:
    validator = validator or ClaimValidator()
    lookup = {chunk.label: chunk for chunk in chunks}
    span_access = access or {
        chunk.source_id: AccessLabel.WORKSPACE for chunk in chunks
    }
    return validator.validate(
        raw, project_id=PROJECT_ID, lookup=lookup, span_access=span_access
    )


def rejection_of(raw: RawClaim, chunks: list[EvidenceChunk]) -> str:
    claim, rejection = validate(raw, chunks)
    assert claim is None, "expected the claim to be rejected"
    assert rejection is not None
    return rejection.code


# ---------------------------------------------------------------------------
# Evidence resolution / citation correctness
# ---------------------------------------------------------------------------
def test_claim_citing_an_unknown_handle_is_rejected() -> None:
    chunk = make_chunk("S1", "The production database is PostgreSQL 13.")
    raw = RawClaim(
        text="The production database is PostgreSQL 13.",
        claim_type="technical_constraint",
        evidence=["S9"],
    )
    assert rejection_of(raw, [chunk]) == "claim_evidence_unknown"


def test_claim_with_no_evidence_is_rejected() -> None:
    chunk = make_chunk("S1", "The production database is PostgreSQL 13.")
    raw = RawClaim(
        text="The production database is PostgreSQL 13.",
        claim_type="technical_constraint",
        evidence=[],
    )
    assert rejection_of(raw, [chunk]) == "claim_evidence_missing"


def test_handle_lookup_is_case_insensitive() -> None:
    chunk = make_chunk("S1", "The production database is PostgreSQL 13.")
    raw = RawClaim(
        text="The production database is PostgreSQL 13.",
        claim_type="technical_constraint",
        evidence=["s1"],
    )
    claim, rejection = validate(raw, [chunk])
    assert rejection is None
    assert claim is not None
    assert claim.source_span_ids == [chunk.span_id]


def test_validated_claim_references_only_real_spans() -> None:
    chunk = make_chunk("S1", "The payments module is owned by Alice.")
    raw = RawClaim(
        text="The payments module is owned by Alice.",
        claim_type="ownership",
        evidence=["S1"],
        confidence=0.9,
    )
    claim, rejection = validate(raw, [chunk])
    assert rejection is None
    assert claim is not None
    assert claim.source_span_ids == [chunk.span_id]
    assert claim.source_ids == [chunk.source_id]
    assert claim.dedup_key == claim_dedup_key(
        ClaimType.OWNERSHIP, claim.text, claim.entity
    )


# ---------------------------------------------------------------------------
# Atomicity
# ---------------------------------------------------------------------------
def test_claim_that_is_too_short_is_rejected() -> None:
    chunk = make_chunk("S1", "Short fact.")
    raw = RawClaim(text="Too short", claim_type="other", evidence=["S1"])
    assert rejection_of(raw, [chunk]) == "claim_text_too_short"


def test_claim_that_is_too_long_is_rejected() -> None:
    chunk = make_chunk("S1", "The billing service owns invoices.")
    raw = RawClaim(text="word " * 100, claim_type="other", evidence=["S1"])
    assert rejection_of(raw, [chunk]) == "claim_text_too_long"


def test_claim_merging_several_facts_is_rejected() -> None:
    chunk = make_chunk("S1", "The billing service owns invoices.")
    raw = RawClaim(
        text="First fact here. Second fact here. Third fact here.",
        claim_type="other",
        evidence=["S1"],
    )
    assert rejection_of(raw, [chunk]) == "claim_merges_multiple_facts"


# ---------------------------------------------------------------------------
# Ownership must be stated, not inferred from a name
# ---------------------------------------------------------------------------
def test_ownership_without_a_cue_is_rejected() -> None:
    # Alice's name appears, but the evidence never assigns ownership.
    chunk = make_chunk("S1", "The payments changelog lists Alice among contributors.")
    raw = RawClaim(
        text="Alice owns the payments module.",
        claim_type="ownership",
        entity="payments",
        evidence=["S1"],
    )
    assert rejection_of(raw, [chunk]) == "claim_ownership_unsupported"


def test_ownership_stated_by_the_evidence_is_accepted() -> None:
    chunk = make_chunk("S1", "The payments module is owned by Alice.")
    raw = RawClaim(
        text="The payments module is owned by Alice.",
        claim_type="ownership",
        entity="payments",
        evidence=["S1"],
    )
    claim, rejection = validate(raw, [chunk])
    assert rejection is None
    assert claim is not None
    assert claim.claim_type is ClaimType.OWNERSHIP


# ---------------------------------------------------------------------------
# Duplicates
# ---------------------------------------------------------------------------
def test_duplicate_claim_in_a_batch_is_rejected_once() -> None:
    chunk = make_chunk("S1", "The production database is PostgreSQL 13.")
    validator = ClaimValidator()
    raw = RawClaim(
        text="The production database is PostgreSQL 13.",
        claim_type="technical_constraint",
        evidence=["S1"],
    )
    first, first_rejection = validate(raw, [chunk], validator=validator)
    second, second_rejection = validate(raw, [chunk], validator=validator)

    assert first is not None and first_rejection is None
    assert second is None
    assert second_rejection is not None
    assert second_rejection.code == "claim_duplicate"


# ---------------------------------------------------------------------------
# Access labels only ever tighten
# ---------------------------------------------------------------------------
def test_derived_claim_inherits_the_strictest_access_label() -> None:
    public = make_chunk("S1", "The billing service owns invoices.")
    restricted = make_chunk("S2", "The incident key rotates every 90 days.")
    raw = RawClaim(
        text="The billing service handles invoices and rotates the incident key.",
        claim_type="operational_procedure",
        evidence=["S1", "S2"],
    )
    claim, rejection = validate(
        raw,
        [public, restricted],
        access={
            public.source_id: AccessLabel.PUBLIC,
            restricted.source_id: AccessLabel.RESTRICTED,
        },
    )
    assert rejection is None
    assert claim is not None
    assert claim.access_label is AccessLabel.RESTRICTED


def test_strictest_access_label_orders_correctly() -> None:
    assert strictest_access_label([]) is AccessLabel.WORKSPACE
    assert strictest_access_label([AccessLabel.PUBLIC]) is AccessLabel.PUBLIC
    assert (
        strictest_access_label([AccessLabel.PUBLIC, AccessLabel.WORKSPACE])
        is AccessLabel.WORKSPACE
    )
    assert (
        strictest_access_label(
            [AccessLabel.PUBLIC, AccessLabel.RESTRICTED, AccessLabel.PRIVATE]
        )
        is AccessLabel.RESTRICTED
    )


# ---------------------------------------------------------------------------
# ExtractorAgent: rejection recording and failure isolation
# ---------------------------------------------------------------------------
def _source(chunk: EvidenceChunk) -> SourceContext:
    return SourceContext(
        source_id=chunk.source_id,
        source_name=chunk.source_name,
        source_type=chunk.source_type,
    )


def _extract(provider, chunks: list[EvidenceChunk], **kwargs):
    source = _source(chunks[0])
    return ExtractorAgent(provider, **kwargs).extract(
        project_id=PROJECT_ID,
        project_name="Handover Project",
        source=source,
        chunks=chunks,
        span_access={chunk.source_id: AccessLabel.WORKSPACE for chunk in chunks},
    )


def test_extractor_keeps_valid_claims_and_records_rejections() -> None:
    chunk = make_chunk("S1", "The production database is PostgreSQL 13.")
    provider = FakeProvider(
        payload={
            "claims": [
                {
                    "text": "The production database is PostgreSQL 13.",
                    "claim_type": "technical_constraint",
                    "evidence": ["S1"],
                    "confidence": 0.9,
                },
                {
                    "text": "The production database is PostgreSQL 15.",
                    "claim_type": "technical_constraint",
                    "evidence": ["S42"],
                    "confidence": 0.9,
                },
            ]
        }
    )
    outcome = _extract(provider, [chunk])
    assert outcome.ok
    assert len(outcome.claims) == 1
    assert [rejection.code for rejection in outcome.rejections] == [
        "claim_evidence_unknown"
    ]


def test_extractor_marks_a_non_json_response_as_an_error() -> None:
    chunk = make_chunk("S1", "The production database is PostgreSQL 13.")
    outcome = _extract(NonJsonFake(), [chunk])
    assert not outcome.ok
    assert outcome.error is not None
    assert outcome.error.code == "ai_unparsable_response"
    assert outcome.claims == []


def test_extractor_reports_a_provider_outage_with_its_code() -> None:
    chunk = make_chunk("S1", "The production database is PostgreSQL 13.")
    outcome = _extract(FailingFake(), [chunk], max_retries=0)
    assert not outcome.ok
    assert outcome.error is not None
    assert outcome.error.code == "ai_unreachable"


def test_extractor_enforces_the_per_source_claim_cap() -> None:
    chunk = make_chunk("S1", "The production database is PostgreSQL 13.")
    provider = FakeProvider(
        payload={
            "claims": [
                {
                    "text": "The production database is PostgreSQL 13.",
                    "claim_type": "technical_constraint",
                    "evidence": ["S1"],
                },
                {
                    "text": "The staging database is PostgreSQL 15.",
                    "claim_type": "technical_constraint",
                    "evidence": ["S1"],
                },
            ]
        }
    )
    outcome = _extract(provider, [chunk], max_claims_per_source=1)
    assert len(outcome.claims) == 1
    assert outcome.error is not None
    assert outcome.error.code == "claim_cap_reached"
