"""Schemas for the Phase 3 project-memory and intelligence endpoints.

Everything returned here is read back from PostgreSQL. There are no sample or
placeholder values: a project that has never been reconstructed reports
``reconstructed: false`` rather than invented statistics.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    AccessLabel,
    ClaimStatus,
    ClaimType,
    ConflictStatus,
    FreshnessStatus,
    HandoverStatus,
    OpenQuestionStatus,
    ProcessingRunStatus,
    SourceType,
    VerificationVerdict,
)
from app.schemas.common import PageMeta


# ---------------------------------------------------------------------------
# Reconstruction
# ---------------------------------------------------------------------------
class ReconstructRequest(BaseModel):
    """Optional narrowing of a reconstruction run to specific sources."""

    source_ids: list[uuid.UUID] | None = Field(
        default=None,
        description=(
            "Restrict the run to these sources. The server still applies the "
            "access filter; unauthorised or restricted sources are dropped."
        ),
    )


class ProcessingRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    status: ProcessingRunStatus
    source_count: int
    claim_count: int
    verified_count: int
    uncertain_count: int
    conflict_count: int
    open_question_count: int
    model_name: str | None = None
    error_message: str | None = None
    errors: list[dict[str, Any]] = Field(default_factory=list)
    stats: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime


class ProcessingRunListResponse(BaseModel):
    items: list[ProcessingRunRead]
    meta: PageMeta


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------
class EvidenceRef(BaseModel):
    """A traceable link from a claim back to an exact region of a source."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_id: uuid.UUID
    span_id: uuid.UUID | None = None
    source_name: str | None = None
    source_type: SourceType | None = None
    source_location: str | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    supporting_quote: str | None = None
    access_label: AccessLabel | None = None
    source_date: datetime | None = None
    author: str | None = None
    metadata: dict[str, Any] = Field(
        default_factory=dict, validation_alias="meta", serialization_alias="metadata"
    )


# ---------------------------------------------------------------------------
# Claims
# ---------------------------------------------------------------------------
class VerificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    verdict: VerificationVerdict
    supporting_quote: str | None = None
    quote_validated: bool
    contradicted_by: list[str] = Field(default_factory=list)
    explanation: str | None = None
    confidence: float | None = None
    model_name: str | None = None
    created_at: datetime


class ClaimHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    action: str
    from_status: ClaimStatus | None = None
    to_status: ClaimStatus | None = None
    note: str | None = None
    actor_id: uuid.UUID | None = None
    metadata: dict[str, Any] = Field(
        default_factory=dict, validation_alias="meta", serialization_alias="metadata"
    )
    created_at: datetime


class ClaimSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    text: str
    claim_type: ClaimType
    entity: str | None = None
    status: ClaimStatus
    critical: bool
    author: str | None = None
    confidence: float | None = None
    reasoning_summary: str | None = None
    access_label: AccessLabel
    reviewed_at: datetime | None = None
    review_note: str | None = None
    verified_at: datetime | None = None
    verified_by_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
    evidence_count: int = 0
    source_date: datetime | None = Field(
        default=None,
        description="Earliest evidence source date — used to order the decision timeline.",
    )


class ClaimDetail(ClaimSummary):
    evidence: list[EvidenceRef] = Field(default_factory=list)
    verifications: list[VerificationRead] = Field(default_factory=list)
    history: list[ClaimHistoryRead] = Field(default_factory=list)
    conflicts: list["ConflictSummary"] = Field(default_factory=list)


class ClaimListResponse(BaseModel):
    items: list[ClaimSummary]
    meta: PageMeta
    status_counts: dict[str, int] = Field(default_factory=dict)
    type_counts: dict[str, int] = Field(default_factory=dict)


class ClaimReviewRequest(BaseModel):
    """A human review decision. Only ``approve`` may produce *Verified*."""

    action: Literal["approve", "reject"]
    note: str | None = Field(default=None, max_length=2000)


# ---------------------------------------------------------------------------
# Conflicts
# ---------------------------------------------------------------------------
class ConflictSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    entity: str | None = None
    claim_type: ClaimType | None = None
    property_key: str | None = None
    kind: str
    status: ConflictStatus
    summary: str | None = None
    resolution_note: str | None = None
    resolved_by_id: uuid.UUID | None = None
    resolved_at: datetime | None = None
    created_at: datetime
    claims: list[ClaimSummary] = Field(default_factory=list)


class ConflictListResponse(BaseModel):
    items: list[ConflictSummary]
    meta: PageMeta


class ConflictResolveRequest(BaseModel):
    """Resolve or dismiss a detected contradiction; the record is preserved."""

    action: Literal["resolve", "dismiss"]
    note: str = Field(min_length=4, max_length=2000)
    chosen_claim_id: uuid.UUID | None = Field(
        default=None,
        description=(
            "When resolving, the claim the reviewer decided is correct. It becomes "
            "Supported and the others in the conflict become Uncertain."
        ),
    )


# ---------------------------------------------------------------------------
# Open questions and freshness
# ---------------------------------------------------------------------------
class OpenQuestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    claim_id: uuid.UUID | None = None
    question: str
    context: str | None = None
    entity: str | None = None
    status: OpenQuestionStatus
    access_label: AccessLabel
    resolution_note: str | None = None
    resolved_at: datetime | None = None
    created_at: datetime


class OpenQuestionListResponse(BaseModel):
    items: list[OpenQuestionRead]
    meta: PageMeta


class StaleSourceRead(BaseModel):
    """A source flagged for freshness review (never silently replaced)."""

    id: uuid.UUID
    source_name: str
    source_type: SourceType
    author: str | None = None
    created_at_source: datetime | None = None
    freshness: FreshnessStatus
    freshness_checked_at: datetime | None = None
    warnings: list[dict[str, Any]] = Field(default_factory=list)


class UncertaintyResponse(BaseModel):
    """The Uncertainty Centre: unsupported claims, questions and stale sources."""

    unsupported_claims: list[ClaimSummary]
    open_questions: list[OpenQuestionRead]
    stale_sources: list[StaleSourceRead]


# ---------------------------------------------------------------------------
# Project memory overview
# ---------------------------------------------------------------------------
class ProjectMemoryRead(BaseModel):
    project_id: uuid.UUID
    reconstructed: bool = False
    version: int | None = None
    summary: str | None = None
    stats: dict[str, Any] = Field(default_factory=dict)
    generated_at: datetime | None = None
    last_run_id: uuid.UUID | None = None
    last_run: ProcessingRunRead | None = None


# ---------------------------------------------------------------------------
# Handover
# ---------------------------------------------------------------------------
class HandoverStatementRead(BaseModel):
    text: str
    claim_ids: list[uuid.UUID] = Field(default_factory=list)


class HandoverSectionRead(BaseModel):
    key: str
    title: str
    statements: list[HandoverStatementRead] = Field(default_factory=list)


class HandoverRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    status: HandoverStatus
    summary: str | None = None
    sections: list[HandoverSectionRead] = Field(default_factory=list)
    claim_ids: list[str] = Field(default_factory=list)
    validation_errors: list[dict[str, Any]] = Field(default_factory=list)
    model_name: str | None = None
    created_at: datetime
    updated_at: datetime


ClaimDetail.model_rebuild()
