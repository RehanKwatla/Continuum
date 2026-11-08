"""Deterministic handover output validation (Phase 4 §9, §10).

The Handover Writer is an LLM, so its output cannot be trusted on its own. This
module is the gate between the model's draft and a stored handover:

* only **approved** (human-verified) claims may be referenced — the approved set is
  loaded from the database and handed to the writer as a fixed list of handles;
* the application — never the model — creates the ``statement_id`` and the
  ``statement_type`` of every statement, and resolves every handle to a real
  claim id plus the exact revision it was approved at;
* a *factual* statement that cannot be linked to an approved claim is **deleted**
  and the rejection is recorded;
* a section with no supported content is not filled with invented prose: it is
  marked ``not_established`` and carries the literal placeholder

      "Information not established from the available evidence."

Nothing in this module can promote a claim's status or widen the approved set.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.contracts import (
    ApprovedClaimRef,
    HandoverInput,
    HandoverSection,
    HandoverStatement,
    HandoverValidation,
    RawHandover,
)
from app.ai.prompts import (
    ADVISORY_SECTIONS,
    HANDOVER_SECTIONS,
    NOT_ESTABLISHED_PLACEHOLDER,
    SECTION_STATEMENT_TYPES,
)
from app.models.claim import Claim
from app.models.enums import ClaimStatus, StatementType

#: Error code recorded when a statement cannot be tied to an approved claim.
_UNLINKED_SENTENCE = "unlinked_sentence"
#: Statement types that must cite at least one approved claim.
_FACT_TYPES: frozenset[str] = frozenset(
    {StatementType.ESTABLISHED_FACT.value, StatementType.SUGGESTED_ACTION.value}
)
_SECTION_TITLES: dict[str, str] = dict(HANDOVER_SECTIONS)


def approved_claim_handles(db: Session, project_id: uuid.UUID) -> HandoverInput:
    """Load the project's approved claims as ``C1``, ``C2`` ... references.

    Only claims in the human-approved state are returned, each tagged with the
    revision the reviewer approved so a later edit invalidates the reference.
    """
    rows = list(
        db.execute(
            select(Claim)
            .where(Claim.project_id == project_id, Claim.status == ClaimStatus.VERIFIED)
            .order_by(Claim.created_at, Claim.id)
        ).scalars().all()
    )
    claims = [
        ApprovedClaimRef(
            handle=f"C{index}",
            claim_id=row.id,
            claim_type=row.claim_type,
            text=row.text,
            revision_number=row.revision_number,
        )
        for index, row in enumerate(rows, start=1)
    ]
    return HandoverInput(claims=claims)


def _statement_type_for(key: str) -> str:
    return SECTION_STATEMENT_TYPES.get(key, StatementType.ESTABLISHED_FACT.value)


def validate_handover(raw: RawHandover, *, approved: HandoverInput) -> HandoverValidation:
    """Keep only the statements that link to an approved claim.

    The returned document always contains every template section, in order. Empty
    sections are flagged rather than filled.
    """
    by_handle = {claim.handle: claim for claim in approved.claims}
    by_handle.update({claim.handle.lower(): claim for claim in approved.claims})

    resolved_sections: dict[str, list[HandoverStatement]] = {
        key: [] for key, _ in HANDOVER_SECTIONS
    }
    errors: list[dict[str, object]] = []
    used: list[uuid.UUID] = []
    revisions: dict[str, int] = {}

    for raw_section in raw.sections:
        key = (raw_section.key or "").strip().lower()
        if key not in resolved_sections:
            errors.append(
                {
                    "code": "unknown_section",
                    "section": key or "(missing)",
                    "message": "Section key is not part of the handover template.",
                }
            )
            continue

        statement_type = _statement_type_for(key)
        for statement in raw_section.statements:
            text = " ".join(statement.text.split())
            if not text:
                continue

            claim_ids: list[uuid.UUID] = []
            statement_revisions: dict[str, int] = {}
            for handle in statement.claim_ids:
                reference = by_handle.get(handle) or by_handle.get(handle.lower())
                if reference is None:
                    continue
                if reference.claim_id not in claim_ids:
                    claim_ids.append(reference.claim_id)
                statement_revisions[str(reference.claim_id)] = reference.revision_number

            if not claim_ids and statement_type in _FACT_TYPES:
                errors.append(
                    {
                        "code": _UNLINKED_SENTENCE,
                        "section": key,
                        "statement_type": statement_type,
                        "text": text[:400],
                        "message": (
                            "Statement rejected: it could not be linked to an "
                            "approved claim."
                        ),
                    }
                )
                continue

            resolved_sections[key].append(
                HandoverStatement(
                    text=text,
                    claim_ids=claim_ids,
                    statement_type=statement_type,
                    claim_revisions=statement_revisions,
                )
            )
            for claim_id in claim_ids:
                if claim_id not in used:
                    used.append(claim_id)
                revisions[str(claim_id)] = statement_revisions[str(claim_id)]

    sections = [
        HandoverSection(
            key=key,
            title=title,
            statements=resolved_sections[key],
            not_established=not resolved_sections[key],
            placeholder=None if resolved_sections[key] else NOT_ESTABLISHED_PLACEHOLDER,
        )
        for key, title in HANDOVER_SECTIONS
    ]

    summary = (raw.summary or "").strip() or None
    if summary and not any(
        _mentions_approved(summary, claim.text) for claim in approved.claims
    ):
        # A summary that cannot be traced to an approved claim is dropped too.
        errors.append(
            {
                "code": _UNLINKED_SENTENCE,
                "section": "summary",
                "text": summary[:400],
                "message": "Summary rejected: no approved claim supports it.",
            }
        )
        summary = None

    return HandoverValidation(
        summary=summary,
        sections=sections,
        claim_ids=used,
        claim_revisions=revisions,
        errors=errors,
    )


def validate_edited_statement(
    text: str, *, claim_ids: list[uuid.UUID], approved_ids: set[uuid.UUID]
) -> tuple[bool, str | None]:
    """Re-validate a reviewer's edit of a factual statement.

    Returns ``(supported, explanation)``. An edit that drops the statement's claim
    references — or cites a claim that is no longer approved — is *not*
    evidence-backed and must be labelled as reviewer-authored instead.
    """
    normalised = " ".join(text.split())
    if not normalised:
        return False, "The statement is empty."
    if not claim_ids:
        return False, "The statement no longer references any approved claim."
    orphans = [str(item) for item in claim_ids if item not in approved_ids]
    if orphans:
        return False, (
            "The statement references claims that are no longer approved: "
            + ", ".join(orphans)
        )
    return True, None


def _mentions_approved(summary: str, claim_text: str) -> bool:
    """Loose check used only for the free-text summary line."""
    summary_words = {word for word in _words(summary) if len(word) > 4}
    claim_words = {word for word in _words(claim_text) if len(word) > 4}
    return len(summary_words & claim_words) >= 2


def _words(text: str) -> list[str]:
    import re

    return [token.casefold() for token in re.findall(r"[A-Za-z0-9]+", text)]


def advisory_section_keys() -> frozenset[str]:
    return ADVISORY_SECTIONS


def section_titles() -> dict[str, str]:
    return dict(_SECTION_TITLES)


def statement_type_for_section(key: str) -> str:
    return _statement_type_for(key)
