"""Validated input/output contracts for the Phase 3 agents.

Two layers are deliberately kept apart:

* **Raw payloads** (``RawClaim``, ``RawVerification``, ``RawHandover``) mirror the
  JSON the model is asked to return. They are parsed *leniently* — a single
  malformed entry must never destroy an otherwise good batch.
* **Validated contracts** (``EvidenceChunk``, ``ExtractedClaim``,
  ``VerificationResult``, ``ConflictFinding`` ...) are what application code
  produces *after* it has checked every reference the model made.

The model never sees a database id. The backend labels each evidence span with a
short, disposable handle (``S1``, ``S2`` ...) and resolves those handles back to
real :class:`~app.models.evidence_span.EvidenceSpan` ids itself. Any handle the
backend cannot resolve marks the claim as fabricated evidence and it is rejected
by :mod:`app.services.claim_validation`.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    AccessLabel,
    ClaimStatus,
    ClaimType,
    FreshnessStatus,
    VerificationVerdict,
)

# ---------------------------------------------------------------------------
# Backend-owned context handed to the agents
# ---------------------------------------------------------------------------
class SourceContext(BaseModel):
    """Serialisable snapshot of one authorised source (no raw secrets)."""

    source_id: uuid.UUID
    source_name: str
    source_type: str
    author: str | None = None
    source_date: datetime | None = None
    access_label: AccessLabel = AccessLabel.WORKSPACE
    span_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceChunk(BaseModel):
    """One backend-owned evidence span, labelled for the model."""

    label: str
    span_id: uuid.UUID
    source_id: uuid.UUID
    source_name: str
    source_type: str
    location: str
    author: str | None = None
    source_date: datetime | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Raw model payloads (lenient)
# ---------------------------------------------------------------------------
class RawClaim(BaseModel):
    model_config = ConfigDict(extra="ignore")

    text: str = ""
    claim_type: str = "other"
    entity: str | None = None
    evidence: list[str] = Field(default_factory=list)
    confidence: float | None = None
    critical: bool = False
    reasoning_summary: str | None = None


class RawVerification(BaseModel):
    model_config = ConfigDict(extra="ignore")

    verdict: str = "none"
    supporting_quote: str | None = None
    contradicted_by: list[str] = Field(default_factory=list)
    explanation: str | None = None
    confidence: float | None = None


class RawHandoverStatement(BaseModel):
    model_config = ConfigDict(extra="ignore")

    text: str = ""
    claim_ids: list[str] = Field(default_factory=list)


class RawHandoverSection(BaseModel):
    model_config = ConfigDict(extra="ignore")

    key: str = ""
    title: str | None = None
    statements: list[RawHandoverStatement] = Field(default_factory=list)


class RawHandover(BaseModel):
    model_config = ConfigDict(extra="ignore")

    sections: list[RawHandoverSection] = Field(default_factory=list)
    summary: str | None = None


def _as_str(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _as_labels(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    labels: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            labels.append(item.strip())
        elif isinstance(item, dict):  # {"span": "S1"} style sloppiness
            for key in ("label", "span", "id", "ref"):
                candidate = item.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    labels.append(candidate.strip())
                    break
    return list(dict.fromkeys(labels))


def parse_raw_claims(payload: dict[str, Any] | None) -> list[RawClaim]:
    """Leniently read ``{"claims": [...]}`` from a model response."""
    if not isinstance(payload, dict):
        return []
    items = payload.get("claims")
    if not isinstance(items, list):
        return []

    claims: list[RawClaim] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        text = _as_str(item.get("text") or item.get("claim") or item.get("statement"))
        if not text:
            continue
        claims.append(
            RawClaim(
                text=text,
                claim_type=_as_str(item.get("claim_type") or item.get("type")) or "other",
                entity=_as_str(item.get("entity")) or None,
                evidence=_as_labels(item.get("evidence") or item.get("source_spans")),
                confidence=_as_float(item.get("confidence")),
                critical=bool(item.get("critical")),
                reasoning_summary=_as_str(
                    item.get("reasoning_summary") or item.get("reasoning")
                )
                or None,
            )
        )
    return claims


def parse_raw_verification(payload: dict[str, Any] | None) -> RawVerification | None:
    if not isinstance(payload, dict):
        return None
    verdict = _as_str(payload.get("verdict")).lower()
    if not verdict:
        return None
    return RawVerification(
        verdict=verdict,
        supporting_quote=_as_str(payload.get("supporting_quote")) or None,
        contradicted_by=_as_labels(payload.get("contradicted_by")),
        explanation=_as_str(payload.get("explanation")) or None,
        confidence=_as_float(payload.get("confidence")),
    )


def parse_raw_handover(payload: dict[str, Any] | None) -> RawHandover:
    if not isinstance(payload, dict):
        return RawHandover()
    sections: list[RawHandoverSection] = []
    raw_sections = payload.get("sections")
    if not isinstance(raw_sections, list):
        return RawHandover()
    for item in raw_sections:
        if not isinstance(item, dict):
            continue
        statements: list[RawHandoverStatement] = []
        for raw_statement in item.get("statements") or []:
            if not isinstance(raw_statement, dict):
                continue
            text = _as_str(raw_statement.get("text"))
            if not text:
                continue
            statements.append(
                RawHandoverStatement(
                    text=text,
                    claim_ids=_as_labels(
                        raw_statement.get("claim_ids") or raw_statement.get("claims")
                    ),
                )
            )
        sections.append(
            RawHandoverSection(
                key=_as_str(item.get("key")),
                title=_as_str(item.get("title")) or None,
                statements=statements,
            )
        )
    return RawHandover(sections=sections, summary=_as_str(payload.get("summary")) or None)


# ---------------------------------------------------------------------------
# Validated contracts produced by application code
# ---------------------------------------------------------------------------
class ExtractedClaim(BaseModel):
    """A claim that has already passed claim validation."""

    local_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    project_id: uuid.UUID
    text: str
    claim_type: ClaimType = ClaimType.OTHER
    entity: str | None = None
    source_span_ids: list[uuid.UUID] = Field(default_factory=list)
    source_ids: list[uuid.UUID] = Field(default_factory=list)
    author: str | None = None
    confidence: float | None = None
    critical: bool = False
    reasoning_summary: str | None = None
    access_label: AccessLabel = AccessLabel.WORKSPACE
    dedup_key: str = ""
    status: ClaimStatus = ClaimStatus.UNCERTAIN
    time_context: datetime | None = None


class VerificationResult(BaseModel):
    """The Verifier's verdict, after server-side quotation validation."""

    claim_local_id: uuid.UUID
    verdict: VerificationVerdict
    supporting_quote: str | None = None
    quote_validated: bool = False
    contradicted_by: list[uuid.UUID] = Field(default_factory=list)
    explanation: str | None = None
    confidence: float | None = None
    model_name: str | None = None


class ConflictFinding(BaseModel):
    """A deterministic contradiction between two or more claims."""

    entity: str | None = None
    claim_type: ClaimType | None = None
    property_key: str | None = None
    kind: str = "value_disagreement"
    summary: str = ""
    claim_local_ids: list[uuid.UUID] = Field(default_factory=list)
    values: dict[str, str] = Field(default_factory=dict)
    time_contexts: dict[str, str] = Field(default_factory=dict)


class StaleWarning(BaseModel):
    """A deterministic staleness signal for one source."""

    source_id: uuid.UUID
    status: FreshnessStatus
    reason: str
    related_source_id: uuid.UUID | None = None


class OpenQuestionDraft(BaseModel):
    question: str
    context: str | None = None
    entity: str | None = None
    dedup_key: str = ""
    access_label: AccessLabel = AccessLabel.WORKSPACE
    claim_local_id: uuid.UUID | None = None


class ProcessingError(BaseModel):
    """A recoverable, per-source or per-stage failure."""

    stage: str
    code: str
    message: str
    source_id: uuid.UUID | None = None


# ---------------------------------------------------------------------------
# Handover contracts
# ---------------------------------------------------------------------------
class ApprovedClaimRef(BaseModel):
    """An approved (human-verified) claim, labelled for the Handover Writer."""

    handle: str
    claim_id: uuid.UUID
    claim_type: ClaimType
    text: str


class HandoverInput(BaseModel):
    """The complete, fixed input for a handover: approved facts + questions."""

    claims: list[ApprovedClaimRef] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)


class HandoverStatement(BaseModel):
    text: str
    claim_ids: list[uuid.UUID] = Field(default_factory=list)


class HandoverSection(BaseModel):
    key: str
    title: str
    statements: list[HandoverStatement] = Field(default_factory=list)


class HandoverValidation(BaseModel):
    """Result of the deterministic output validator."""

    summary: str | None = None
    sections: list[HandoverSection] = Field(default_factory=list)
    claim_ids: list[uuid.UUID] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)

    @property
    def accepted_statements(self) -> int:
        return sum(len(section.statements) for section in self.sections)
