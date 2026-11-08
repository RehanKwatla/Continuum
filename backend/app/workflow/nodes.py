"""Node implementations for the Phase 3 reconstruction workflow.

Each node is a plain, testable method that takes the typed
:class:`~app.workflow.state.ReconstructionState`, does one deterministic job and
returns the state. Nothing here talks to a vendor SDK — the only model access is
through the injected :class:`~app.ai.provider.LLMProvider`.

Access control happens **before** any content reaches a prompt
(:meth:`WorkflowNodes.access_filter`): membership is enforced by the API layer,
and this node applies the source-level filter (explicit selection plus the
``restricted`` access label) so unauthorised text can never enter the workflow.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.contracts import (
    EvidenceChunk,
    ExtractedClaim,
    OpenQuestionDraft,
    ProcessingError,
    SourceContext,
    StaleWarning,
)
from app.ai.extractor import ExtractorAgent
from app.ai.provider import LLMProvider
from app.ai.verifier import VerifierAgent
from app.models.claim import Claim
from app.models.claim_history import ClaimHistory
from app.models.conflict import Conflict, ConflictClaim
from app.models.enums import (
    AccessLabel,
    ClaimStatus,
    ClaimType,
    ConflictStatus,
    OpenQuestionStatus,
    ProcessingRunStatus,
    VerificationVerdict,
    WorkspaceRole,
)
from app.models.evidence import Evidence
from app.models.evidence_span import EvidenceSpan
from app.models.open_question import OpenQuestion
from app.models.processing_run import ProcessingRun
from app.models.project import Project
from app.models.project_memory import ProjectMemory
from app.models.source import Source
from app.models.verification import Verification
from app.models.workspace import WorkspaceMember
from app.services.claim_validation import question_dedup_key
from app.services.conflict_detector import ConflictDetector
from app.services.evidence_span_service import EvidenceSpanService
from app.services.handover_validator import approved_claim_handles
from app.services.staleness_service import StalenessDetector
from app.workflow.state import (
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_INSUFFICIENT,
    STATUS_PARTIAL,
    STATUS_RUNNING,
    ReconstructionState,
)

logger = logging.getLogger("continuum.workflow")

#: Roles allowed to include ``restricted`` sources in a reconstruction run.
_RESTRICTED_ROLES: tuple[WorkspaceRole, ...] = (WorkspaceRole.ADMIN, WorkspaceRole.OWNER)


def status_from_verification(verdict: VerificationVerdict, contradicted: bool) -> ClaimStatus:
    """Map a Verifier verdict onto a *non-human* claim status.

    ``supports`` yields *Supported* — never *Verified*.
    """
    if verdict is VerificationVerdict.SUPPORTS:
        return ClaimStatus.SUPPORTED
    if verdict is VerificationVerdict.NONE and contradicted:
        return ClaimStatus.CONFLICT
    return ClaimStatus.UNCERTAIN


class WorkflowNodes:
    """The ten nodes of the reconstruction graph, bound to a DB session."""

    def __init__(self, db: Session, provider: LLMProvider) -> None:
        self.db = db
        self.provider = provider
        self.extractor = ExtractorAgent(provider)
        self.verifier = VerifierAgent(provider)

    # ------------------------------------------------------------------
    # 1. access_filter
    # ------------------------------------------------------------------
    def access_filter(self, state: ReconstructionState) -> ReconstructionState:
        """Load only the sources the requesting user is authorised to use."""
        project = self.db.get(Project, state.project_id)
        if project is None:
            state.workflow_status = STATUS_FAILED
            state.add_error(
                ProcessingError(
                    stage="access_filter",
                    code="project_not_found",
                    message="The project could not be loaded for this run.",
                )
            )
            return state

        state.project_name = project.name
        state.workspace_id = project.workspace_id

        role = self._workspace_role(project.workspace_id, state.requesting_user_id)
        if role is None:
            state.workflow_status = STATUS_FAILED
            state.add_error(
                ProcessingError(
                    stage="access_filter",
                    code="workspace_membership_required",
                    message="The requesting user is not a member of this workspace.",
                )
            )
            return state

        rows = list(
            self.db.execute(
                select(Source).where(Source.project_id == state.project_id)
            ).scalars().all()
        )
        selected = set(state.authorised_source_ids)

        authorised: list[SourceContext] = []
        skipped: list[dict[str, Any]] = []
        for source in rows:
            if selected and source.id not in selected:
                continue
            if source.access_label is AccessLabel.RESTRICTED and role not in _RESTRICTED_ROLES:
                skipped.append({"source_id": str(source.id), "reason": "restricted_label"})
                continue
            if not (source.content or "").strip():
                skipped.append({"source_id": str(source.id), "reason": "no_content"})
                continue
            authorised.append(self._source_context(source))

        state.source_records = authorised
        state.authorised_source_ids = [context.source_id for context in authorised]
        state.stats["filtered_out"] = skipped
        # Terminal status is set by the *node*, not the router: LangGraph only
        # keeps the value a node returns, so a status written in a router would
        # be lost and the run would be reported as completed.
        state.workflow_status = STATUS_RUNNING if authorised else STATUS_INSUFFICIENT
        return state

    # ------------------------------------------------------------------
    # 2. prepare_source_spans
    # ------------------------------------------------------------------
    def prepare_source_spans(self, state: ReconstructionState) -> ReconstructionState:
        """Create/collect the backend-owned evidence spans for each source."""
        if not state.source_records:
            return state

        service = EvidenceSpanService(self.db)
        chunks: list[EvidenceChunk] = []
        index = 0
        for context in state.source_records:
            source = self.db.get(Source, context.source_id)
            if source is None:  # pragma: no cover - deleted mid-run
                continue
            try:
                spans = service.ensure_spans(source)
            except Exception as exc:  # per-source isolation
                logger.exception("Span preparation failed for source %s", context.source_id)
                self.db.rollback()
                state.add_error(
                    ProcessingError(
                        stage="prepare_source_spans",
                        code="span_preparation_failed",
                        message=str(exc)[:300],
                        source_id=context.source_id,
                    )
                )
                continue

            context.span_count = len(spans)
            for span in spans:
                index += 1
                label = f"S{index}"
                state.span_access[span.id] = source.access_label
                state.span_to_label[label] = str(span.id)
                chunks.append(
                    EvidenceChunk(
                        label=label,
                        span_id=span.id,
                        source_id=source.id,
                        source_name=source.source_name,
                        source_type=source.source_type.value,
                        location=span.location,
                        author=source.author,
                        source_date=context.source_date,
                        start_offset=span.start_offset,
                        end_offset=span.end_offset,
                        text=span.text,
                        metadata=dict(span.meta or {}),
                    )
                )
        state.evidence_records = chunks
        if not chunks:
            state.workflow_status = STATUS_INSUFFICIENT
        return state

    # ------------------------------------------------------------------
    # 3. extract_claims
    # ------------------------------------------------------------------
    def extract_claims(self, state: ReconstructionState) -> ReconstructionState:
        """Run the Extractor per source, isolating per-source failures."""
        by_source: dict[uuid.UUID, list[EvidenceChunk]] = {}
        for chunk in state.evidence_records:
            by_source.setdefault(chunk.source_id, []).append(chunk)

        for context in state.source_records:
            chunks = by_source.get(context.source_id) or []
            if not chunks:
                state.add_error(
                    ProcessingError(
                        stage="extract_claims",
                        code="no_evidence_spans",
                        message="The source produced no traceable evidence spans.",
                        source_id=context.source_id,
                    )
                )
                continue
            try:
                outcome = self.extractor.extract(
                    project_id=state.project_id,
                    project_name=state.project_name,
                    source=context,
                    chunks=chunks,
                    span_access=state.span_access,
                )
            except Exception as exc:  # pragma: no cover - defensive isolation
                logger.exception("Extraction crashed for source %s", context.source_id)
                state.add_error(
                    ProcessingError(
                        stage="extract_claims",
                        code="extraction_failed",
                        message=str(exc)[:300],
                        source_id=context.source_id,
                    )
                )
                continue

            state.extracted_claims.extend(outcome.claims)
            state.model_name = outcome.model_name or state.model_name
            for rejection in outcome.rejections:
                state.rejected_claims.append(
                    {
                        "code": rejection.code,
                        "message": rejection.message,
                        "text": rejection.text[:400],
                        "source_id": str(context.source_id),
                    }
                )
            if outcome.error is not None:
                state.add_error(outcome.error)
        return state

    # ------------------------------------------------------------------
    # 4. validate_claims
    # ------------------------------------------------------------------
    def validate_claims(self, state: ReconstructionState) -> ReconstructionState:
        """Cross-source deduplication plus reconciliation with stored claims."""
        unique: dict[str, ExtractedClaim] = {}
        for claim in state.extracted_claims:
            existing = unique.get(claim.dedup_key)
            if existing is None:
                unique[claim.dedup_key] = claim
                continue
            # Same fact seen in a second source: keep one claim, cite both spans.
            merged_spans = list(
                dict.fromkeys([*existing.source_span_ids, *claim.source_span_ids])
            )
            merged_sources = list(dict.fromkeys([*existing.source_ids, *claim.source_ids]))
            existing.source_span_ids = merged_spans
            existing.source_ids = merged_sources
            existing.critical = existing.critical or claim.critical
            if claim.confidence is not None:
                existing.confidence = max(existing.confidence or 0.0, claim.confidence)
            state.rejected_claims.append(
                {
                    "code": "claim_duplicate",
                    "message": "The same claim was extracted from another source; "
                    "evidence was merged instead of storing a second claim.",
                    "text": claim.text[:400],
                    "source_id": str(claim.source_ids[0]) if claim.source_ids else None,
                }
            )

        claims = list(unique.values())
        for claim in claims:
            claim.status = ClaimStatus.UNCERTAIN
        state.extracted_claims = claims
        return state

    # ------------------------------------------------------------------
    # 5. verify_claims
    # ------------------------------------------------------------------
    def verify_claims(self, state: ReconstructionState) -> ReconstructionState:
        """Verify each claim against the exact spans it cites."""
        results = []
        for claim in state.extracted_claims:
            chunks = state.chunks_for_claim(claim)
            try:
                result, error = self.verifier.verify(claim=claim, chunks=chunks)
            except Exception as exc:  # pragma: no cover - defensive isolation
                logger.exception("Verification crashed for claim %s", claim.local_id)
                state.add_error(
                    ProcessingError(
                        stage="verify_claims",
                        code="verification_failed",
                        message=str(exc)[:300],
                    )
                )
                claim.status = ClaimStatus.UNCERTAIN
                continue

            if error is not None:
                state.add_error(error)
                claim.status = ClaimStatus.UNCERTAIN
                continue
            if result is None:  # pragma: no cover - defensive
                continue

            claim.status = status_from_verification(
                result.verdict, bool(result.contradicted_by)
            )
            results.append(result)

        state.verification_results = results
        if state.extracted_claims and not results:
            # Claims existed but none could be verified: the run is partial.
            state.workflow_status = STATUS_PARTIAL
        return state

    # ------------------------------------------------------------------
    # 6. detect_conflicts
    # ------------------------------------------------------------------
    def detect_conflicts(self, state: ReconstructionState) -> ReconstructionState:
        """Deterministic, time-aware contradiction detection."""
        findings = ConflictDetector().detect(state.extracted_claims)
        state.detected_conflicts = findings

        conflicting: set[uuid.UUID] = set()
        for finding in findings:
            if finding.kind != "value_disagreement":
                continue
            conflicting.update(finding.claim_local_ids)

        for claim in state.extracted_claims:
            if claim.local_id in conflicting:
                claim.status = ClaimStatus.CONFLICT
        return state

    # ------------------------------------------------------------------
    # 7. detect_stale_information
    # ------------------------------------------------------------------
    def detect_stale_information(self, state: ReconstructionState) -> ReconstructionState:
        state.stale_warnings = StalenessDetector().detect(
            sources=state.source_records,
            claims=state.extracted_claims,
            conflicts=state.detected_conflicts,
        )
        return state

    # ------------------------------------------------------------------
    # 8. persist_project_memory
    # ------------------------------------------------------------------
    def persist_project_memory(self, state: ReconstructionState) -> ReconstructionState:
        """Write claims, evidence, verifications, conflicts and memory stats."""
        claim_ids = self._persist_claims(state)
        self._persist_verifications(state, claim_ids)
        self._persist_conflicts(state, claim_ids)
        self._persist_freshness(state)
        self._persist_memory_row(state)
        return state

    # ------------------------------------------------------------------
    # 9. create_open_questions
    # ------------------------------------------------------------------
    def create_open_questions(self, state: ReconstructionState) -> ReconstructionState:
        """Persist the questions the sources raise but do not answer."""
        drafts: list[OpenQuestionDraft] = []
        for claim in state.extracted_claims:
            if claim.claim_type is not ClaimType.OPEN_QUESTION:
                continue
            drafts.append(
                OpenQuestionDraft(
                    question=claim.text,
                    context=claim.reasoning_summary,
                    entity=claim.entity,
                    dedup_key=question_dedup_key(claim.text, claim.entity),
                    access_label=claim.access_label,
                    claim_local_id=claim.local_id,
                )
            )

        if not drafts:
            state.open_questions = []
            return state

        existing_keys = {
            key
            for (key,) in self.db.execute(
                select(OpenQuestion.dedup_key).where(
                    OpenQuestion.project_id == state.project_id,
                    OpenQuestion.dedup_key.is_not(None),
                )
            ).all()
        }

        stored: list[OpenQuestionDraft] = []
        for draft in drafts:
            if draft.dedup_key in existing_keys:
                continue
            self.db.add(
                OpenQuestion(
                    project_id=state.project_id,
                    run_id=state.run_id,
                    claim_id=self._stored_claim_id(state, draft.claim_local_id),
                    question=draft.question,
                    context=draft.context,
                    entity=draft.entity,
                    dedup_key=draft.dedup_key,
                    status=OpenQuestionStatus.OPEN,
                    access_label=draft.access_label,
                )
            )
            existing_keys.add(draft.dedup_key)
            stored.append(draft)
        self.db.flush()
        state.open_questions = stored
        return state

    # ------------------------------------------------------------------
    # 10. prepare_handover_input
    # ------------------------------------------------------------------
    def prepare_handover_input(self, state: ReconstructionState) -> ReconstructionState:
        """Collect approved claims only, so the Handover Writer has a fixed input."""
        handover_input = approved_claim_handles(self.db, state.project_id)
        handover_input.questions = [
            row.question
            for row in self.db.execute(
                select(OpenQuestion)
                .where(
                    OpenQuestion.project_id == state.project_id,
                    OpenQuestion.status == OpenQuestionStatus.OPEN,
                )
                .order_by(OpenQuestion.created_at)
            ).scalars().all()
        ]
        state.handover_input = handover_input
        if state.workflow_status == STATUS_RUNNING:
            state.workflow_status = STATUS_COMPLETED
        return state

    # ==================================================================
    # Helpers
    # ==================================================================
    def _workspace_role(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> WorkspaceRole | None:
        membership = self.db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
            )
        ).scalar_one_or_none()
        return membership.role if membership else None

    @staticmethod
    def _source_context(source: Source) -> SourceContext:
        return SourceContext(
            source_id=source.id,
            source_name=source.source_name,
            source_type=source.source_type.value,
            author=source.author,
            source_date=source.created_at_source or source.created_at,
            access_label=source.access_label,
            metadata=dict(source.meta or {}),
        )

    def _persist_claims(self, state: ReconstructionState) -> dict[str, uuid.UUID]:
        """Insert new claims, or attach evidence to an existing identical claim."""
        claim_ids: dict[str, uuid.UUID] = {}
        chunk_by_span = {chunk.span_id: chunk for chunk in state.evidence_records}

        for claim in state.extracted_claims:
            existing = self.db.execute(
                select(Claim).where(
                    Claim.project_id == state.project_id,
                    Claim.dedup_key == claim.dedup_key,
                )
            ).scalar_one_or_none()

            if existing is not None:
                claim_ids[str(claim.local_id)] = existing.id
                state.persisted_claim_ids[str(claim.local_id)] = str(existing.id)
                self.db.add(
                    ClaimHistory(
                        claim_id=existing.id,
                        run_id=state.run_id,
                        action="deduped",
                        from_status=existing.status,
                        to_status=existing.status,
                        note="Reprocessing found the same claim again; evidence was merged.",
                        meta={"run_id": str(state.run_id) if state.run_id else None},
                    )
                )
                row = existing
            else:
                row = Claim(
                    project_id=state.project_id,
                    run_id=state.run_id,
                    text=claim.text,
                    claim_type=claim.claim_type,
                    entity=claim.entity,
                    status=claim.status,
                    critical=claim.critical,
                    author=claim.author,
                    confidence=claim.confidence,
                    reasoning_summary=claim.reasoning_summary,
                    access_label=claim.access_label,
                    dedup_key=claim.dedup_key,
                )
                self.db.add(row)
                self.db.flush()
                claim_ids[str(claim.local_id)] = row.id
                state.persisted_claim_ids[str(claim.local_id)] = str(row.id)
                self.db.add(
                    ClaimHistory(
                        claim_id=row.id,
                        run_id=state.run_id,
                        action="extracted",
                        to_status=row.status,
                        note="Claim extracted from authorised project sources.",
                    )
                )

            existing_spans = {
                span_id
                for (span_id,) in self.db.execute(
                    select(Evidence.span_id).where(Evidence.claim_id == row.id)
                ).all()
            }
            for span_id in claim.source_span_ids:
                if span_id in existing_spans:
                    continue
                chunk = chunk_by_span.get(span_id)
                if chunk is None:
                    continue
                self.db.add(
                    Evidence(
                        claim_id=row.id,
                        source_id=chunk.source_id,
                        span_id=chunk.span_id,
                        source_location=chunk.location[:500],
                        start_offset=chunk.start_offset,
                        end_offset=chunk.end_offset,
                        supporting_quote=chunk.text,
                    )
                )
                existing_spans.add(span_id)

        self.db.flush()
        return claim_ids

    def _persist_verifications(
        self, state: ReconstructionState, claim_ids: dict[str, uuid.UUID]
    ) -> None:
        for result in state.verification_results:
            claim_id = claim_ids.get(str(result.claim_local_id))
            if claim_id is None:
                continue
            self.db.add(
                Verification(
                    claim_id=claim_id,
                    run_id=state.run_id,
                    verdict=result.verdict,
                    supporting_quote=result.supporting_quote,
                    quote_validated=result.quote_validated,
                    contradicted_by=[str(item) for item in result.contradicted_by],
                    explanation=result.explanation,
                    confidence=result.confidence,
                    model_name=result.model_name,
                )
            )
            self.db.add(
                ClaimHistory(
                    claim_id=claim_id,
                    run_id=state.run_id,
                    action="verified",
                    to_status=self._status_of(state, result.claim_local_id),
                    note=f"Verifier verdict: {result.verdict.value}.",
                    meta={"quote_validated": result.quote_validated},
                )
            )
        self.db.flush()

    def _persist_conflicts(
        self, state: ReconstructionState, claim_ids: dict[str, uuid.UUID]
    ) -> None:
        for finding in state.detected_conflicts:
            row = Conflict(
                project_id=state.project_id,
                run_id=state.run_id,
                entity=finding.entity,
                claim_type=finding.claim_type,
                property_key=finding.property_key,
                kind=finding.kind,
                status=(
                    ConflictStatus.OPEN
                    if finding.kind == "value_disagreement"
                    else ConflictStatus.DISMISSED
                ),
                summary=finding.summary,
                resolution_note=(
                    None
                    if finding.kind == "value_disagreement"
                    else "Automatically classified as a change over time, not a contradiction."
                ),
            )
            self.db.add(row)
            self.db.flush()
            for local_id in finding.claim_local_ids:
                claim_id = claim_ids.get(str(local_id))
                if claim_id is None:
                    continue
                self.db.add(
                    ConflictClaim(conflict_id=row.id, claim_id=claim_id)
                )
                if finding.kind == "value_disagreement":
                    self.db.add(
                        ClaimHistory(
                            claim_id=claim_id,
                            run_id=state.run_id,
                            action="conflict_flagged",
                            to_status=ClaimStatus.CONFLICT,
                            note=finding.summary[:500],
                            meta={"conflict_id": str(row.id)},
                        )
                    )
        self.db.flush()

    def _persist_freshness(self, state: ReconstructionState) -> None:
        from datetime import datetime, timezone

        for warning in state.stale_warnings:
            source = self.db.get(Source, warning.source_id)
            if source is None:
                continue
            source.freshness = warning.status
            source.freshness_checked_at = datetime.now(timezone.utc)
            source.warnings = [
                *(source.warnings or []),
                {
                    "kind": "freshness",
                    "reason": warning.reason,
                    "status": warning.status.value,
                },
            ][-20:]
        self.db.flush()

    def _persist_memory_row(self, state: ReconstructionState) -> None:
        from datetime import datetime, timezone

        type_counts: dict[str, int] = {}
        status_counts: dict[str, int] = {}
        for claim in state.extracted_claims:
            type_counts[claim.claim_type.value] = type_counts.get(claim.claim_type.value, 0) + 1
            status_counts[claim.status.value] = status_counts.get(claim.status.value, 0) + 1

        memory = self.db.execute(
            select(ProjectMemory).where(ProjectMemory.project_id == state.project_id)
        ).scalar_one_or_none()
        if memory is None:
            memory = ProjectMemory(project_id=state.project_id)
            self.db.add(memory)
            self.db.flush()
        else:
            memory.version = (memory.version or 1) + 1

        memory.last_run_id = state.run_id
        memory.generated_at = datetime.now(timezone.utc)
        memory.stats = {
            "claim_count": len(state.extracted_claims),
            "source_count": len(state.source_records),
            "span_count": len(state.evidence_records),
            "by_type": type_counts,
            "by_status": status_counts,
            "conflict_count": sum(
                1 for item in state.detected_conflicts if item.kind == "value_disagreement"
            ),
            "ownership_changes": sum(
                1 for item in state.detected_conflicts if item.kind == "changed_over_time"
            ),
            "stale_count": len(state.stale_warnings),
            # ``create_open_questions`` runs after this node, so count the
            # open-question claims directly rather than the not-yet-built list.
            "open_question_count": sum(
                1
                for claim in state.extracted_claims
                if claim.claim_type is ClaimType.OPEN_QUESTION
            ),
            "rejected_count": len(state.rejected_claims),
            "model": state.model_name,
        }
        memory.summary = self._summary(memory.stats)
        self.db.flush()

    @staticmethod
    def _summary(stats: dict[str, Any]) -> str:
        return (
            f"Reconstructed {stats.get('claim_count', 0)} claims from "
            f"{stats.get('source_count', 0)} sources: "
            f"{stats.get('by_status', {}).get(ClaimStatus.SUPPORTED.value, 0)} supported, "
            f"{stats.get('by_status', {}).get(ClaimStatus.UNCERTAIN.value, 0)} uncertain, "
            f"{stats.get('by_status', {}).get(ClaimStatus.CONFLICT.value, 0)} in conflict. "
            f"{stats.get('conflict_count', 0)} open conflict(s), "
            f"{stats.get('stale_count', 0)} source(s) flagged for freshness review."
        )

    def _stored_claim_id(
        self, state: ReconstructionState, local_id: uuid.UUID | None
    ) -> uuid.UUID | None:
        if local_id is None:
            return None
        raw = state.persisted_claim_ids.get(str(local_id))
        return uuid.UUID(raw) if raw else None

    @staticmethod
    def _status_of(state: ReconstructionState, local_id: uuid.UUID) -> ClaimStatus | None:
        claim = state.claim_by_local_id(local_id)
        return claim.status if claim else None

    # ------------------------------------------------------------------
    # Run bookkeeping
    # ------------------------------------------------------------------
    def finalise_run(self, state: ReconstructionState) -> None:
        """Update the :class:`ProcessingRun` row once the graph has finished."""
        finalise_run(self.db, state)


def finalise_run(db: Session, state: ReconstructionState) -> None:
    """Update the :class:`ProcessingRun` row once the graph has finished."""
    if state.run_id is None:
        return
    from datetime import datetime, timezone

    run = db.get(ProcessingRun, state.run_id)
    if run is None:  # pragma: no cover - deleted mid-run
        return

    status_counts: dict[str, int] = {}
    for claim in state.extracted_claims:
        status_counts[claim.status.value] = status_counts.get(claim.status.value, 0) + 1

    run.status = _run_status(state)
    run.source_count = len(state.source_records)
    run.claim_count = len(state.extracted_claims)
    # ``verified_count`` counts *human-verified* claims only. A model ``supports``
    # verdict produces a *Supported* claim, never a *Verified* one, so the two are
    # reported separately and a supported claim is never presented as verified.
    run.verified_count = status_counts.get(ClaimStatus.VERIFIED.value, 0)
    run.uncertain_count = status_counts.get(ClaimStatus.UNCERTAIN.value, 0)
    run.conflict_count = sum(
        1 for item in state.detected_conflicts if item.kind == "value_disagreement"
    )
    run.open_question_count = len(state.open_questions)
    run.model_name = state.model_name
    run.errors = [error.model_dump(mode="json") for error in state.processing_errors]
    run.stats = {
        **state.stats,
        "by_status": status_counts,
        "supported_count": status_counts.get(ClaimStatus.SUPPORTED.value, 0),
        "verified_count": status_counts.get(ClaimStatus.VERIFIED.value, 0),
        "span_count": len(state.evidence_records),
        "stale_count": len(state.stale_warnings),
        "ownership_changes": sum(
            1 for item in state.detected_conflicts if item.kind == "changed_over_time"
        ),
        "rejected_claims": state.rejected_claims[:50],
        "rejected_count": len(state.rejected_claims),
    }
    if state.processing_errors and run.status is ProcessingRunStatus.COMPLETED:
        run.status = ProcessingRunStatus.PARTIAL
    if run.status is ProcessingRunStatus.FAILED:
        run.error_message = state.processing_errors[0].message if state.processing_errors else None
    run.finished_at = datetime.now(timezone.utc)
    db.flush()


def _run_status(state: ReconstructionState) -> ProcessingRunStatus:
    if state.workflow_status == STATUS_FAILED:
        return ProcessingRunStatus.FAILED
    if state.workflow_status == STATUS_INSUFFICIENT:
        return ProcessingRunStatus.PARTIAL
    if state.processing_errors:
        return ProcessingRunStatus.PARTIAL
    if state.workflow_status == STATUS_PARTIAL:
        return ProcessingRunStatus.PARTIAL
    return ProcessingRunStatus.COMPLETED
