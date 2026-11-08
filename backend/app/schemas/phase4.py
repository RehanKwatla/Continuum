"""Typed contracts for the human review, approval and successor handover APIs.

Everything here describes data that is actually read back from PostgreSQL. AI
*verification* and human *approval* are modelled as separate fields — a
verification verdict never becomes an approval on its own.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import (
    ClaimStatus,
    ClaimType,
    ConflictResolution,
    ConflictStatus,
    HandoverLifecycleStatus,
    ReviewDecision,
    StatementType,
)
from app.schemas.common import PageMeta

# ---------------------------------------------------------------------------
# Human review queue (§3)
# ---------------------------------------------------------------------------
class ReviewQueueItem(BaseModel):
    """One claim as it appears in the human review queue."""

    id: uuid.UUID
    text: str
    category: ClaimType
    critical: bool
    ai_verdict: str | None = Field(
        default=None, description="The AI verifier's evidence assessment (not an approval)."
    )
    evidence_count: int
    source_references: list[str]
    conflict_status: str
    stale_warning: bool
    created_at: datetime
    #: Human-facing review status ("Approved" for Verified, "Pending review", ...).
    review_status: str
    status: ClaimStatus
    revision_number: int = 1


class ReviewQueueResponse(BaseModel):
    items: list[ReviewQueueItem]
    meta: PageMeta


class ClaimDecisionRequest(BaseModel):
    """A single human review decision (Phase 4 §4, §7)."""

    decision: Literal["approve", "reject", "clarification", "request_evidence"]
    explanation: str | None = Field(default=None, max_length=2000)


class ClaimActionRequest(BaseModel):
    """Body of the dedicated approve / reject / request-clarification actions.

    The action itself is in the URL; only the reviewer's explanation (and, for
    a clarification, whether fresh evidence was asked for) travels in the body.
    """

    explanation: str | None = Field(default=None, max_length=2000)
    request_evidence: bool = Field(
        default=False,
        description="Ask for additional evidence rather than a plain clarification.",
    )


class ClaimEditRequest(BaseModel):
    """A reviewer's correction of a claim; always recorded as a new revision."""

    text: str | None = Field(default=None, max_length=4000)
    claim_type: ClaimType | None = None
    entity: str | None = Field(default=None, max_length=300)
    note: str = Field(
        min_length=4,
        max_length=2000,
        description="Why the reviewer changed the statement (required).",
    )


class ClaimRevisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    revision_number: int
    text: str
    claim_type: ClaimType
    entity: str | None = None
    note: str | None = None
    created_by_id: uuid.UUID | None = None
    is_material: bool
    verification_required: bool
    created_at: datetime


class ClaimDecisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    claim_id: uuid.UUID
    claim_revision_id: uuid.UUID | None = None
    reviewer_id: uuid.UUID | None = None
    decision: ReviewDecision
    explanation: str | None = None
    from_status: str | None = None
    to_status: str | None = None
    metadata: dict[str, Any] = Field(
        default_factory=dict, validation_alias="meta", serialization_alias="metadata"
    )
    created_at: datetime


# ---------------------------------------------------------------------------
# Conflict Resolution Centre (§6)
# ---------------------------------------------------------------------------
class ConflictClaimRead(BaseModel):
    """One side of a contradiction, with the evidence that supports it."""

    id: uuid.UUID
    text: str
    claim_type: ClaimType
    entity: str | None = None
    status: ClaimStatus
    author: str | None = None
    confidence: float | None = None
    created_at: datetime
    source_date: datetime | None = None
    evidence: list[dict[str, Any]] = Field(default_factory=list)


class ConflictDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    entity: str | None = None
    claim_type: ClaimType | None = None
    property_key: str | None = None
    kind: str
    status: ConflictStatus
    summary: str | None = None
    resolution: str | None = None
    resolution_label: str | None = None
    resolution_note: str | None = None
    resolution_metadata: dict[str, Any] = Field(
        default_factory=dict, validation_alias="resolution_meta", serialization_alias="resolution_metadata"
    )
    resolved_by_id: uuid.UUID | None = None
    resolved_at: datetime | None = None
    created_at: datetime
    #: True when the two statements could both be true of different periods.
    could_be_temporal_change: bool = False
    claims: list[ConflictClaimRead] = Field(default_factory=list)


class ConflictResolutionRequest(BaseModel):
    """One of the five reviewer outcomes; an explanation is always required."""

    resolution: ConflictResolution = Field(
        description=(
            "claim_a_accepted | claim_b_accepted | both_valid_in_different_time_periods "
            "| both_rejected | more_information_required | dismissed"
        )
    )
    note: str = Field(min_length=4, max_length=2000)
    chosen_claim_id: uuid.UUID | None = Field(
        default=None,
        description="The claim accepted, when the reviewer accepted one side.",
    )

    @model_validator(mode="after")
    def _require_accepted_claim(self) -> "ConflictResolutionRequest":
        """Accepting one side is meaningless without naming which side that is.

        The service layer re-checks this against the claims actually linked to
        the conflict; enforcing it here too means an obviously incomplete
        request is rejected before it reaches business logic.
        """
        if self.resolution in (
            ConflictResolution.ACCEPT_A,
            ConflictResolution.ACCEPT_B,
        ) and self.chosen_claim_id is None:
            raise ValueError(
                "Accepting one claim requires 'chosen_claim_id' — the id of the "
                "claim the reviewer decided is correct."
            )
        return self


# ---------------------------------------------------------------------------
# Versioned handover (§8–§12)
# ---------------------------------------------------------------------------
class HandoverStatementModel(BaseModel):
    """One statement of a handover version, carrying its provenance."""

    statement_id: str
    text: str
    statement_type: StatementType
    claim_ids: list[uuid.UUID] = Field(default_factory=list)
    claim_revisions: dict[str, int] = Field(default_factory=dict)
    #: Kept when a reviewer edits generated text, so the original is never lost.
    original_text: str | None = None
    reviewer_edited: bool = False
    #: Set when the deterministic validator could not substantiate the statement.
    unsupported: bool = False


class HandoverSectionModel(BaseModel):
    key: str
    title: str
    statements: list[HandoverStatementModel] = Field(default_factory=list)
    not_established: bool = False
    placeholder: str | None = None
    removed: bool = False


class ReviewerNoteModel(BaseModel):
    id: str
    text: str
    author_id: uuid.UUID | None = None
    created_at: datetime | None = None


class HandoverVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    handover_id: uuid.UUID
    version_number: int
    status: HandoverLifecycleStatus
    summary: str | None = None
    model_name: str | None = None
    generated_by_id: uuid.UUID | None = None
    approved_by_id: uuid.UUID | None = None
    approved_at: datetime | None = None
    included_claim_ids: list[uuid.UUID] = Field(default_factory=list)
    claim_revisions: dict[str, int] = Field(default_factory=dict)
    validation_errors: list[dict[str, Any]] = Field(default_factory=list)
    reviewer_notes: list[ReviewerNoteModel] = Field(default_factory=list)
    sections: list[HandoverSectionModel] = Field(default_factory=list)
    created_at: datetime


class HandoverDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    status: HandoverLifecycleStatus
    current_version: int
    created_by_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
    current: HandoverVersionRead | None = None


class HandoverListResponse(BaseModel):
    items: list[HandoverDetail]
    meta: PageMeta


class HandoverStatementInput(BaseModel):
    statement_id: str | None = None
    text: str = Field(min_length=1, max_length=4000)
    claim_ids: list[uuid.UUID] = Field(default_factory=list)
    original_text: str | None = None


class HandoverSectionInput(BaseModel):
    key: str
    title: str | None = Field(default=None, max_length=300)
    statements: list[HandoverStatementInput] = Field(default_factory=list)
    removed: bool = False


class HandoverUpdateRequest(BaseModel):
    """A reviewer's edit of the current draft; always saved as a new version."""

    title: str | None = Field(default=None, max_length=300)
    summary: str | None = Field(default=None, max_length=4000)
    sections: list[HandoverSectionInput]
    reviewer_notes: list[str] = Field(
        default_factory=list,
        description="Reviewer-authored notes appended to this version (never project facts).",
    )
    note: str | None = Field(
        default=None, max_length=2000, description="Why the reviewer changed the document."
    )


class HandoverGenerateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=300)


class HandoverPublishRequest(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


# ---------------------------------------------------------------------------
# Audit trail (§15)
# ---------------------------------------------------------------------------
class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID | None = None
    workspace_id: uuid.UUID | None = None
    action: str
    resource_type: str | None = None
    resource_id: uuid.UUID | None = None
    metadata: dict[str, Any] = Field(
        default_factory=dict, validation_alias="meta", serialization_alias="metadata"
    )
    created_at: datetime


class AuditTrailResponse(BaseModel):
    items: list[AuditLogRead]
    meta: PageMeta


class HandoverExportAudit(BaseModel):
    format: Literal["markdown", "pdf"]
