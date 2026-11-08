"""Claim validation — the gate every extracted claim must pass.

The LLM never gets to store a claim. Between the model and the database sits
this module, which is plain application code and therefore deterministic:

* **Evidence references are resolved by the backend.** The model cites labels
  (``S1``); this module maps them to real ``evidence_spans`` rows. An
  unresolvable label is a fabricated citation and the claim is rejected.
* **Atomicity is enforced.** A claim that is actually three sentences of
  unrelated fact is rejected rather than stored.
* **Ownership is not inferred from a name.** An ``ownership``/``responsibility``
  claim whose evidence contains no ownership cue is rejected.
* **Access labels only ever tighten.** A derived claim inherits the strictest
  access label of the sources it cites.

Every rejection is returned as a coded :class:`ClaimRejection` so the workflow can
record *why* knowledge was discarded instead of silently dropping it.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass

from app.ai.contracts import EvidenceChunk, ExtractedClaim, RawClaim
from app.ai.prompts import claim_type_from_model
from app.models.enums import AccessLabel, ClaimType

#: Longest text still considered a single atomic claim.
MAX_CLAIM_CHARS = 400
#: Shortest text accepted as a meaningful claim.
MIN_CLAIM_CHARS = 12
#: More sentence terminators than this means several facts were merged.
MAX_SENTENCE_ENDINGS = 2

_WHITESPACE_RE = re.compile(r"\s+")
_SENTENCE_END_RE = re.compile(r"[.!?](?:\s|$)")
_ENTITY_RE = re.compile(r"[^a-z0-9]+")

#: Wording that actually indicates ownership/responsibility.
_OWNERSHIP_CUES: tuple[str, ...] = (
    "own",
    "owns",
    "owned",
    "owner",
    "ownership",
    "responsible",
    "responsibility",
    "maintain",
    "maintains",
    "maintainer",
    "lead",
    "leads",
    "leads on",
    "in charge",
    "accountable",
    "handles",
    "handle",
    "manages",
    "manage",
    "managed by",
    "contact",
    "point of contact",
    "escalation",
    "reviewer",
    "reviewed by",
    "assigned",
    "assignee",
    "dri",
)

#: Access labels from least to most restrictive.
_ACCESS_ORDER: tuple[AccessLabel, ...] = (
    AccessLabel.PUBLIC,
    AccessLabel.WORKSPACE,
    AccessLabel.PRIVATE,
    AccessLabel.RESTRICTED,
)


@dataclass(frozen=True)
class ClaimRejection:
    """A claim the backend refused to store, with a machine-readable reason."""

    code: str
    message: str
    text: str


def normalise_text(text: str) -> str:
    """Case- and whitespace-insensitive form used for deduplication."""
    return _WHITESPACE_RE.sub(" ", text).strip().casefold()


def normalise_entity(entity: str | None) -> str | None:
    if not entity:
        return None
    cleaned = _WHITESPACE_RE.sub(" ", entity).strip()
    if not cleaned:
        return None
    return cleaned[:300]


def claim_dedup_key(claim_type: ClaimType, text: str, entity: str | None) -> str:
    """Stable 64-char key so the same claim is never stored twice per project."""
    entity_key = _ENTITY_RE.sub("-", (entity or "").casefold()).strip("-")
    payload = f"{claim_type.value}\x1f{entity_key}\x1f{normalise_text(text)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def strictest_access_label(labels: list[AccessLabel]) -> AccessLabel:
    """Return the most restrictive label in ``labels`` (default WORKSPACE)."""
    if not labels:
        return AccessLabel.WORKSPACE
    return max(labels, key=lambda item: _ACCESS_ORDER.index(item))


def question_dedup_key(question: str, entity: str | None = None) -> str:
    payload = f"{_ENTITY_RE.sub('-', (entity or '').casefold())}\x1f{normalise_text(question)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sentence_count(text: str) -> int:
    return len(_SENTENCE_END_RE.findall(text))


def is_atomic(text: str) -> tuple[bool, str | None]:
    """Deterministic atomicity check. Returns ``(ok, reason)``."""
    stripped = text.strip()
    if len(stripped) < MIN_CLAIM_CHARS:
        return False, "claim_text_too_short"
    if len(stripped) > MAX_CLAIM_CHARS:
        return False, "claim_text_too_long"
    if sentence_count(stripped) > MAX_SENTENCE_ENDINGS:
        return False, "claim_merges_multiple_facts"
    return True, None


def has_ownership_cue(texts: list[str]) -> bool:
    """True when the cited evidence actually assigns ownership."""
    haystack = " ".join(texts).casefold()
    return any(cue in haystack for cue in _OWNERSHIP_CUES)


class ClaimValidator:
    """Stateful validator: resolves evidence handles and deduplicates a batch."""

    def __init__(self) -> None:
        self._seen_keys: set[str] = set()

    def reset(self) -> None:
        self._seen_keys.clear()

    def resolve_spans(
        self, handles: list[str], lookup: dict[str, EvidenceChunk]
    ) -> tuple[list[EvidenceChunk], list[str]]:
        """Map model handles onto real spans, returning ``(spans, unknown)``."""
        resolved: list[EvidenceChunk] = []
        unknown: list[str] = []
        for handle in handles:
            chunk = lookup.get(handle.strip().upper()) or lookup.get(handle.strip())
            if chunk is None:
                unknown.append(handle)
                continue
            resolved.append(chunk)
        return resolved, unknown

    def validate(
        self,
        raw: RawClaim,
        *,
        project_id: uuid.UUID,
        lookup: dict[str, EvidenceChunk],
        span_access: dict[uuid.UUID, AccessLabel],
    ) -> tuple[ExtractedClaim | None, ClaimRejection | None]:
        """Validate one raw claim. Exactly one of the two results is ``None``."""
        text = _WHITESPACE_RE.sub(" ", raw.text).strip()
        claim_type = claim_type_from_model(raw.claim_type)
        entity = normalise_entity(raw.entity)

        ok, reason = is_atomic(text)
        if not ok:
            return None, ClaimRejection(
                code=reason or "claim_not_atomic",
                message=f"Claim text is not a single atomic fact ({reason}).",
                text=text,
            )

        if not raw.evidence:
            return None, ClaimRejection(
                code="claim_evidence_missing",
                message="Claim cites no evidence span.",
                text=text,
            )

        spans, unknown = self.resolve_spans(raw.evidence, lookup)
        if unknown:
            return None, ClaimRejection(
                code="claim_evidence_unknown",
                message=(
                    "Claim cites evidence handles the backend did not provide: "
                    + ", ".join(sorted(unknown))
                ),
                text=text,
            )
        if not spans:
            return None, ClaimRejection(
                code="claim_evidence_missing",
                message="None of the cited spans could be resolved.",
                text=text,
            )

        if claim_type in {ClaimType.OWNERSHIP, ClaimType.RESPONSIBILITY}:
            if not has_ownership_cue([span.text for span in spans]):
                return None, ClaimRejection(
                    code="claim_ownership_unsupported",
                    message=(
                        "Ownership/responsibility was not stated by the evidence; a "
                        "name appearing in a file is not proof of ownership."
                    ),
                    text=text,
                )

        dedup_key = claim_dedup_key(claim_type, text, entity)
        if dedup_key in self._seen_keys:
            return None, ClaimRejection(
                code="claim_duplicate",
                message="An identical claim was already extracted in this run.",
                text=text,
            )
        self._seen_keys.add(dedup_key)

        source_ids = list(dict.fromkeys(span.source_id for span in spans))
        labels = [span_access.get(span.source_id, AccessLabel.WORKSPACE) for span in spans]
        dates = [span.source_date for span in spans if span.source_date is not None]
        authors = [span.author for span in spans if span.author]

        confidence = raw.confidence
        if confidence is None:
            confidence = 0.5
        confidence = min(max(float(confidence), 0.0), 1.0)

        return (
            ExtractedClaim(
                project_id=project_id,
                text=text,
                claim_type=claim_type,
                entity=entity,
                source_span_ids=[span.span_id for span in spans],
                source_ids=source_ids,
                author=authors[0] if authors else None,
                confidence=confidence,
                critical=bool(raw.critical),
                reasoning_summary=(raw.reasoning_summary or None),
                access_label=strictest_access_label(labels),
                dedup_key=dedup_key,
                time_context=min(dates) if dates else None,
            ),
            None,
        )
