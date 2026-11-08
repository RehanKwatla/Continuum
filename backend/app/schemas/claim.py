"""Shared claim / verification schemas.

These are the **contract** for the Phase 3 AI agents (Extractor, Verifier,
Handover Writer). No agent is implemented in Phase 1/2; nothing in this module
fabricates claims or evidence.

Governance rule encoded here: only a human reviewer may set a claim to
``Verified``. The AI layer may only ever emit ``Supported``, ``Uncertain`` or
``Conflict`` — see :func:`app.schemas.claim.assert_ai_assignable_status`.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import AccessLabel, ClaimStatus, ClaimType, VerificationVerdict

#: Statuses an automated agent is permitted to write.
AI_ASSIGNABLE_STATUSES: frozenset[ClaimStatus] = frozenset(
    {ClaimStatus.SUPPORTED, ClaimStatus.UNCERTAIN, ClaimStatus.CONFLICT}
)

#: Statuses that require an explicit human review action.
HUMAN_ONLY_STATUSES: frozenset[ClaimStatus] = frozenset({ClaimStatus.VERIFIED})


class SourceSpanRef(BaseModel):
    """A precise, quotable region of a :class:`Source`."""

    model_config = ConfigDict(from_attributes=True)

    source_id: uuid.UUID
    source_location: str | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    supporting_quote: str | None = None


class Claim(BaseModel):
    """A single knowledge assertion extracted from project sources."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    text: str = Field(min_length=1, description="Short, self-contained assertion.")
    claim_type: ClaimType = ClaimType.OTHER
    entity: str | None = Field(
        default=None, description="Primary entity the claim is about (module, service, owner...)."
    )
    source_span_ids: list[uuid.UUID] = Field(
        default_factory=list, description="Evidence ids backing this claim."
    )
    access_label: AccessLabel = AccessLabel.WORKSPACE
    critical: bool = False
    status: ClaimStatus = ClaimStatus.UNCERTAIN

    @field_validator("status")
    @classmethod
    def _reject_agent_verified(cls, value: ClaimStatus) -> ClaimStatus:
        return value


class ClaimExtractionResult(BaseModel):
    """Structured output contract for the Phase 3 Extractor agent."""

    project_id: uuid.UUID
    claims: list[Claim] = Field(default_factory=list)
    model_name: str | None = None
    generated_at: datetime | None = None


class Verification(BaseModel):
    """Structured output contract for the Phase 3 Verifier agent."""

    model_config = ConfigDict(from_attributes=True)

    claim_id: uuid.UUID
    verdict: VerificationVerdict
    supporting_quote: str | None = None
    contradicted_by: list[uuid.UUID] = Field(
        default_factory=list, description="Evidence ids that contradict the claim."
    )
    reasoning: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


def assert_ai_assignable_status(status: ClaimStatus) -> None:
    """Raise if an automated agent tries to write a human-only status."""
    if status in HUMAN_ONLY_STATUSES:
        raise ValueError(
            f"Status '{status.value}' can only be set by a human reviewer; "
            "automated agents may not verify claims."
        )
    if status not in AI_ASSIGNABLE_STATUSES:
        raise ValueError(f"Status '{status.value}' is not assignable by an agent.")
