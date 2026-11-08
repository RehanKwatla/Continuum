"""Shared, typed workflow state for the Phase 3 LangGraph reconstruction graph.

One Pydantic model carries the entire run. Agents never exchange free-form
messages: each node reads validated fields, does its work and returns the same
state with those fields extended.

The state is deliberately free of credentials: the model provider is injected
into the graph builder, not carried in the state, and no secret is ever written
into a field that reaches a prompt.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.ai.contracts import (
    ConflictFinding,
    EvidenceChunk,
    ExtractedClaim,
    HandoverInput,
    OpenQuestionDraft,
    ProcessingError,
    SourceContext,
    StaleWarning,
    VerificationResult,
)
from app.models.enums import AccessLabel

#: Terminal statuses written into ``workflow_status``.
STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_PARTIAL = "partial"
STATUS_FAILED = "failed"
STATUS_INSUFFICIENT = "insufficient_sources"


class ReconstructionState(BaseModel):
    """Validated state flowing through every node of the graph."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    # --- identity & access (set before the graph runs) ------------------
    project_id: uuid.UUID
    project_name: str = ""
    workspace_id: uuid.UUID
    requesting_user_id: uuid.UUID
    authorised_source_ids: list[uuid.UUID] = Field(default_factory=list)

    # --- workflow data --------------------------------------------------
    source_records: list[SourceContext] = Field(default_factory=list)
    evidence_records: list[EvidenceChunk] = Field(default_factory=list)
    extracted_claims: list[ExtractedClaim] = Field(default_factory=list)
    verification_results: list[VerificationResult] = Field(default_factory=list)
    detected_conflicts: list[ConflictFinding] = Field(default_factory=list)
    stale_warnings: list[StaleWarning] = Field(default_factory=list)
    open_questions: list[OpenQuestionDraft] = Field(default_factory=list)
    processing_errors: list[ProcessingError] = Field(default_factory=list)

    # --- bookkeeping ----------------------------------------------------
    workflow_status: str = STATUS_PENDING
    run_id: uuid.UUID | None = None
    model_name: str | None = None
    span_access: dict[uuid.UUID, AccessLabel] = Field(default_factory=dict)
    span_to_label: dict[str, str] = Field(default_factory=dict)
    rejected_claims: list[dict[str, Any]] = Field(default_factory=list)
    persisted_claim_ids: dict[str, str] = Field(default_factory=dict)
    handover_input: HandoverInput | None = None
    stats: dict[str, Any] = Field(default_factory=dict)

    # -- helpers -------------------------------------------------------
    def add_error(self, error: ProcessingError) -> None:
        self.processing_errors.append(error)

    def claim_by_local_id(self, local_id: uuid.UUID) -> ExtractedClaim | None:
        for claim in self.extracted_claims:
            if claim.local_id == local_id:
                return claim
        return None

    def chunk_by_span_id(self, span_id: uuid.UUID) -> EvidenceChunk | None:
        for chunk in self.evidence_records:
            if chunk.span_id == span_id:
                return chunk
        return None

    def chunks_for_claim(self, claim: ExtractedClaim) -> list[EvidenceChunk]:
        wanted = set(claim.source_span_ids)
        return [chunk for chunk in self.evidence_records if chunk.span_id in wanted]
