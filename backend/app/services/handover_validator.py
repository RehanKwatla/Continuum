"""Deterministic handover output validation.

The Handover Writer is an LLM, so its output cannot be trusted on its own. This
module is the gate between the model's draft and a stored handover:

* only **approved** (human-verified) claims may be referenced — the approved set is
  loaded from the database and handed to the writer as a fixed list of handles;
* every sentence must resolve to at least one of those handles, otherwise the
  sentence is **deleted** and the rejection is recorded;
* the writer can never widen the approved set, and nothing here can promote a
  claim's status.
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
from app.ai.prompts import ADVISORY_SECTIONS, HANDOVER_SECTIONS
from app.models.claim import Claim
from app.models.enums import ClaimStatus

_UNLINKED_SENTENCE = "unlinked_sentence"
_SECTION_TITLES: dict[str, str] = dict(HANDOVER_SECTIONS)


def approved_claim_handles(db: Session, project_id: uuid.UUID) -> HandoverInput:
    """Load the project's approved claims as ``C1``, ``C2`` ... references."""
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
        )
        for index, row in enumerate(rows, start=1)
    ]
    return HandoverInput(claims=claims)


def validate_handover(raw: RawHandover, *, approved: HandoverInput) -> HandoverValidation:
    """Keep only the sentences that link to an approved claim."""
    by_handle = {claim.handle: claim for claim in approved.claims}
    by_handle.update({claim.handle.lower(): claim for claim in approved.claims})

    resolved_sections: dict[str, list[HandoverStatement]] = {
        key: [] for key, _ in HANDOVER_SECTIONS
    }
    errors: list[dict[str, object]] = []
    used: list[uuid.UUID] = []

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

        for statement in raw_section.statements:
            text = " ".join(statement.text.split())
            if not text:
                continue
            claim_ids: list[uuid.UUID] = []
            for handle in statement.claim_ids:
                reference = by_handle.get(handle) or by_handle.get(handle.lower())
                if reference is not None and reference.claim_id not in claim_ids:
                    claim_ids.append(reference.claim_id)
            if not claim_ids:
                errors.append(
                    {
                        "code": _UNLINKED_SENTENCE,
                        "section": key,
                        "text": text[:400],
                        "message": (
                            "Sentence rejected: it could not be linked to an approved claim."
                        ),
                    }
                )
                continue
            resolved_sections[key].append(
                HandoverStatement(text=text, claim_ids=claim_ids)
            )
            for claim_id in claim_ids:
                if claim_id not in used:
                    used.append(claim_id)

    sections = [
        HandoverSection(key=key, title=title, statements=resolved_sections[key])
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
        summary=summary, sections=sections, claim_ids=used, errors=errors
    )


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
