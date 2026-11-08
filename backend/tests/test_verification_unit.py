"""Verifier-agent unit tests (scripted provider, no network).

The Verifier proposes a verdict; application code decides whether it is
admissible. These tests pin that behaviour down:

* a quotation that is not verbatim collapses the verdict to ``none``;
* a contradiction handle the backend never issued is dropped;
* a verdict maps to *Supported*, never *Verified*.
"""

from __future__ import annotations

import uuid

from app.ai.contracts import EvidenceChunk, ExtractedClaim
from app.ai.verifier import VerifierAgent
from app.models.enums import ClaimStatus, ClaimType, VerificationVerdict
from app.workflow.nodes import status_from_verification

from fake_provider import FailingFake, FakeProvider, NonJsonFake

SPAN_TEXT = "The production database is PostgreSQL 13."


def make_chunk(label: str = "S1", text: str = SPAN_TEXT) -> EvidenceChunk:
    return EvidenceChunk(
        label=label,
        span_id=uuid.uuid4(),
        source_id=uuid.uuid4(),
        source_name="architecture-notes.md",
        source_type="uploaded_markdown",
        location="lines 3-4",
        text=text,
    )


def make_claim(text: str = SPAN_TEXT, span_id: uuid.UUID | None = None) -> ExtractedClaim:
    return ExtractedClaim(
        project_id=uuid.uuid4(),
        text=text,
        claim_type=ClaimType.TECHNICAL_CONSTRAINT,
        entity="database",
        source_span_ids=[span_id] if span_id else [],
    )


def verify(provider, claim: ExtractedClaim, chunks: list[EvidenceChunk]):
    return VerifierAgent(provider, max_retries=0).verify(claim=claim, chunks=chunks)


# ---------------------------------------------------------------------------
# Quotation validation
# ---------------------------------------------------------------------------
def test_verbatim_quotation_is_accepted_as_supporting() -> None:
    chunk = make_chunk()
    provider = FakeProvider(
        payload={
            "verdict": "supports",
            "supporting_quote": SPAN_TEXT,
            "contradicted_by": [],
            "explanation": "The span states the version.",
        }
    )
    result, error = verify(provider, make_claim(span_id=chunk.span_id), [chunk])
    assert error is None
    assert result is not None
    assert result.verdict is VerificationVerdict.SUPPORTS
    assert result.quote_validated is True
    assert result.supporting_quote == SPAN_TEXT


def test_paraphrased_quotation_collapses_the_verdict_to_none() -> None:
    chunk = make_chunk()
    provider = FakeProvider(
        payload={
            "verdict": "supports",
            "supporting_quote": "the database runs postgres thirteen",
            "contradicted_by": [],
            "explanation": "Close enough.",
        }
    )
    result, error = verify(provider, make_claim(span_id=chunk.span_id), [chunk])
    assert error is None
    assert result is not None
    assert result.verdict is VerificationVerdict.NONE
    assert result.quote_validated is False
    assert result.supporting_quote is None
    assert "verbatim" in (result.explanation or "").casefold()


def test_unknown_verdict_string_normalises_to_none() -> None:
    chunk = make_chunk()
    provider = FakeProvider(
        payload={"verdict": "definitely-true", "contradicted_by": []}
    )
    result, error = verify(provider, make_claim(span_id=chunk.span_id), [chunk])
    assert error is None
    assert result is not None
    assert result.verdict is VerificationVerdict.NONE


# ---------------------------------------------------------------------------
# Contradiction handles are resolved by the backend
# ---------------------------------------------------------------------------
def test_unissued_contradiction_handle_is_dropped() -> None:
    chunk = make_chunk()
    provider = FakeProvider(
        payload={"verdict": "none", "contradicted_by": ["S9"]}
    )
    result, error = verify(provider, make_claim(span_id=chunk.span_id), [chunk])
    assert error is None
    assert result is not None
    assert result.contradicted_by == []


def test_issued_contradiction_handle_is_resolved() -> None:
    chunk = make_chunk()
    provider = FakeProvider(
        payload={"verdict": "none", "contradicted_by": ["S1"]}
    )
    result, error = verify(provider, make_claim(span_id=chunk.span_id), [chunk])
    assert error is None
    assert result is not None
    assert result.contradicted_by == [chunk.span_id]


# ---------------------------------------------------------------------------
# Degenerate inputs and outages
# ---------------------------------------------------------------------------
def test_claim_without_retrievable_evidence_stays_uncertain() -> None:
    result, error = verify(FakeProvider(), make_claim(), [])
    assert error is None
    assert result is not None
    assert result.verdict is VerificationVerdict.NONE
    assert result.quote_validated is False


def test_non_json_verification_response_is_an_error() -> None:
    chunk = make_chunk()
    result, error = verify(NonJsonFake(), make_claim(span_id=chunk.span_id), [chunk])
    assert result is None
    assert error is not None
    assert error.code == "ai_unparsable_response"


def test_provider_outage_is_reported_with_its_code() -> None:
    chunk = make_chunk()
    result, error = verify(FailingFake(), make_claim(span_id=chunk.span_id), [chunk])
    assert result is None
    assert error is not None
    assert error.code == "ai_unreachable"


# ---------------------------------------------------------------------------
# A verdict can never reach Verified
# ---------------------------------------------------------------------------
def test_supports_maps_to_supported_and_never_verified() -> None:
    assert (
        status_from_verification(VerificationVerdict.SUPPORTS, contradicted=False)
        is ClaimStatus.SUPPORTED
    )
    # Support is never "verified", regardless of a contradiction flag.
    assert (
        status_from_verification(VerificationVerdict.SUPPORTS, contradicted=True)
        is ClaimStatus.SUPPORTED
    )
    assert (
        status_from_verification(VerificationVerdict.NONE, contradicted=True)
        is ClaimStatus.CONFLICT
    )
    assert (
        status_from_verification(VerificationVerdict.NONE, contradicted=False)
        is ClaimStatus.UNCERTAIN
    )
    assert (
        status_from_verification(VerificationVerdict.PARTLY, contradicted=False)
        is ClaimStatus.UNCERTAIN
    )


def test_no_verdict_can_ever_produce_a_verified_status() -> None:
    produced = {
        status_from_verification(verdict, contradicted)
        for verdict in VerificationVerdict
        for contradicted in (True, False)
    }
    assert ClaimStatus.VERIFIED not in produced
