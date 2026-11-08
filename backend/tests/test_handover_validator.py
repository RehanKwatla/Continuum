"""Handover Writer output-validator unit tests.

The writer is an LLM, so its draft is untrusted. ``validate_handover`` is the
deterministic gate: every sentence must link to an *approved* (human-verified)
claim, and the writer can never widen the approved set or introduce a new fact.
"""

from __future__ import annotations

import uuid

from app.ai.contracts import (
    ApprovedClaimRef,
    HandoverInput,
    RawHandover,
    RawHandoverSection,
    RawHandoverStatement,
)
from app.models.claim import Claim
from app.models.enums import ClaimStatus, ClaimType
from app.services.handover_validator import (
    approved_claim_handles,
    section_titles,
    validate_handover,
)

from synthetic_project import create_tenant

APPROVED_ID = uuid.uuid4()
APPROVED_TEXT = "The production database is PostgreSQL 15."


def approved_input() -> HandoverInput:
    return HandoverInput(
        claims=[
            ApprovedClaimRef(
                handle="C1",
                claim_id=APPROVED_ID,
                claim_type=ClaimType.TECHNICAL_CONSTRAINT,
                text=APPROVED_TEXT,
            )
        ]
    )


def statement(text: str, claim_ids: list[str]) -> RawHandoverStatement:
    return RawHandoverStatement(text=text, claim_ids=claim_ids)


def section(key: str, *statements: RawHandoverStatement) -> RawHandoverSection:
    return RawHandoverSection(key=key, statements=list(statements))


# ---------------------------------------------------------------------------
# Linking
# ---------------------------------------------------------------------------
def test_a_statement_linked_to_an_approved_claim_is_kept() -> None:
    raw = RawHandover(
        sections=[section("decisions", statement(APPROVED_TEXT, ["C1"]))]
    )
    result = validate_handover(raw, approved=approved_input())

    decisions = next(item for item in result.sections if item.key == "decisions")
    assert len(decisions.statements) == 1
    assert decisions.statements[0].claim_ids == [APPROVED_ID]
    assert result.claim_ids == [APPROVED_ID]
    assert result.errors == []


def test_handle_lookup_is_case_insensitive() -> None:
    raw = RawHandover(
        sections=[section("decisions", statement(APPROVED_TEXT, ["c1"]))]
    )
    result = validate_handover(raw, approved=approved_input())
    assert result.accepted_statements == 1
    assert result.claim_ids == [APPROVED_ID]


def test_a_statement_citing_an_unapproved_handle_is_rejected() -> None:
    raw = RawHandover(
        sections=[section("decisions", statement("The database is PostgreSQL 18.", ["C9"]))]
    )
    result = validate_handover(raw, approved=approved_input())
    assert result.accepted_statements == 0
    assert result.claim_ids == []
    assert [error["code"] for error in result.errors] == ["unlinked_sentence"]


def test_a_statement_citing_no_handle_is_rejected() -> None:
    raw = RawHandover(
        sections=[section("overview", statement("Something nobody approved.", []))]
    )
    result = validate_handover(raw, approved=approved_input())
    assert result.accepted_statements == 0
    assert [error["code"] for error in result.errors] == ["unlinked_sentence"]


def test_the_writer_cannot_reference_a_claim_by_its_raw_identifier() -> None:
    # Only the handle the backend issued is acceptable; a guessed id is rejected.
    raw = RawHandover(
        sections=[section("decisions", statement(APPROVED_TEXT, [str(APPROVED_ID)]))]
    )
    result = validate_handover(raw, approved=approved_input())
    assert result.accepted_statements == 0
    assert [error["code"] for error in result.errors] == ["unlinked_sentence"]


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------
def test_an_unknown_section_key_is_reported_and_dropped() -> None:
    raw = RawHandover(
        sections=[section("made_up", statement(APPROVED_TEXT, ["C1"]))]
    )
    result = validate_handover(raw, approved=approved_input())
    assert result.accepted_statements == 0
    assert [error["code"] for error in result.errors] == ["unknown_section"]


def test_every_template_section_is_always_present_in_order() -> None:
    result = validate_handover(RawHandover(), approved=approved_input())
    expected = list(section_titles().items())
    assert [(item.key, item.title) for item in result.sections] == expected


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
def test_an_untraceable_summary_is_dropped() -> None:
    raw = RawHandover(
        summary="The team should celebrate this release with a party."
    )
    result = validate_handover(raw, approved=approved_input())
    assert result.summary is None
    assert any(
        error["code"] == "unlinked_sentence" and error["section"] == "summary"
        for error in result.errors
    )


def test_a_traceable_summary_is_kept() -> None:
    raw = RawHandover(summary="The production database version is recorded.")
    result = validate_handover(raw, approved=approved_input())
    assert result.summary == "The production database version is recorded."
    assert result.errors == []


# ---------------------------------------------------------------------------
# Approved set is loaded from the database
# ---------------------------------------------------------------------------
def _claim(
    db, project_id: uuid.UUID, text: str, status: ClaimStatus, dedup_key: str
) -> Claim:
    row = Claim(
        project_id=project_id,
        text=text,
        claim_type=ClaimType.OTHER,
        status=status,
        dedup_key=dedup_key,
    )
    db.add(row)
    db.flush()
    return row


def test_approved_handles_include_only_verified_claims(db_session) -> None:
    tenant = create_tenant(db_session)
    verified_a = _claim(
        db_session,
        tenant.project.id,
        "The production database is PostgreSQL 15.",
        ClaimStatus.VERIFIED,
        "key-a",
    )
    supported = _claim(
        db_session,
        tenant.project.id,
        "The payments module is owned by Bob.",
        ClaimStatus.SUPPORTED,
        "key-b",
    )
    uncertain = _claim(
        db_session,
        tenant.project.id,
        "The legacy invoices table still needs to be migrated.",
        ClaimStatus.UNCERTAIN,
        "key-c",
    )
    verified_b = _claim(
        db_session,
        tenant.project.id,
        "Webhook retries are capped at three attempts.",
        ClaimStatus.VERIFIED,
        "key-d",
    )

    handover_input = approved_claim_handles(db_session, tenant.project.id)
    ids = [reference.claim_id for reference in handover_input.claims]
    assert set(ids) == {verified_a.id, verified_b.id}
    assert supported.id not in ids
    assert uncertain.id not in ids
    # Handles are issued in a stable sequence.
    assert sorted(reference.handle for reference in handover_input.claims) == [
        "C1",
        "C2",
    ]
