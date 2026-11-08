"""Project-memory service: reconstruction runs, reads and human review.

Two governance rules are enforced here rather than in the UI:

* a reconstruction run **never** produces a *Verified* claim — only
  :meth:`review_claim` can do that, and only for a claim that has evidence;
* a human review can never be silently overwritten by a model: re-verifying an
  approved claim is rejected, and a rejected claim returns to *Uncertain*.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, inspect as sa_inspect, select
from sqlalchemy.orm import Session

from app.ai.contracts import EvidenceChunk, ExtractedClaim
from app.ai.handover_writer import HandoverWriterAgent
from app.ai.provider import LLMProvider
from app.ai.verifier import VerifierAgent
from app.core.errors import ConflictError, NotFoundError, UpstreamError, ValidationAppError
from app.models.claim import Claim
from app.models.claim_history import ClaimHistory
from app.models.audit import AuditLog
from app.models.conflict import Conflict, ConflictClaim
from app.models.enums import (
    AccessLabel,
    ClaimStatus,
    ClaimType,
    ConflictStatus,
    FreshnessStatus,
    HandoverStatus,
    OpenQuestionStatus,
    ProcessingRunStatus,
)
from app.models.evidence import Evidence
from app.models.evidence_span import EvidenceSpan
from app.models.handover import HandoverDocument
from app.models.open_question import OpenQuestion
from app.models.processing_run import ProcessingRun
from app.models.project import Project
from app.models.project_memory import ProjectMemory
from app.models.source import Source
from app.models.user import User
from app.models.verification import Verification
from app.schemas.memory import (
    ClaimDetail,
    ClaimHistoryRead,
    ClaimSummary,
    ConflictSummary,
    EvidenceRef,
    OpenQuestionRead,
    ProjectMemoryRead,
    ProcessingRunRead,
    StaleSourceRead,
    UncertaintyResponse,
    VerificationRead,
)
from app.schemas.phase4 import ConflictClaimRead, ConflictDetail
from app.services import claim_state_machine as machine
from app.services.handover_validator import approved_claim_handles
from app.services.review_service import ReviewService
from app.workflow.graph import build_reconstruction_graph
from app.workflow.nodes import finalise_run, status_from_verification
from app.workflow.state import ReconstructionState

logger = logging.getLogger("continuum.memory")

#: Claim statuses that are still awaiting a human decision.
_UNRESOLVED_STATUSES: tuple[ClaimStatus, ...] = (
    ClaimStatus.UNCERTAIN,
    ClaimStatus.CONFLICT,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Reconstruction
# ---------------------------------------------------------------------------
def reconstruct_project(
    db: Session,
    *,
    project: Project,
    user: User,
    provider: LLMProvider,
    source_ids: list[uuid.UUID] | None = None,
) -> tuple[ProcessingRun, ReconstructionState]:
    """Run the LangGraph reconstruction workflow for one project."""
    run = ProcessingRun(
        project_id=project.id,
        requested_by_id=user.id,
        status=ProcessingRunStatus.RUNNING,
        started_at=_now(),
    )
    db.add(run)
    db.commit()

    state = ReconstructionState(
        project_id=project.id,
        project_name=project.name,
        workspace_id=project.workspace_id,
        requesting_user_id=user.id,
        authorised_source_ids=list(source_ids or []),
        run_id=run.id,
    )

    try:
        graph = build_reconstruction_graph(db, provider)
        result = graph.invoke(state)
    except Exception as exc:  # pragma: no cover - defensive; graph isolates per source
        logger.exception("Reconstruction run %s crashed", run.id)
        run.status = ProcessingRunStatus.FAILED
        run.error_message = str(exc)[:1000]
        run.finished_at = _now()
        db.commit()
        raise

    final = (
        result
        if isinstance(result, ReconstructionState)
        else ReconstructionState.model_validate(result)
    )
    finalise_run(db, final)
    db.commit()
    db.refresh(run)
    return run, final


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------
class MemoryService:
    """Read access and human review for reconstructed project knowledge."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # -- overview ------------------------------------------------------
    def memory_overview(self, project_id: uuid.UUID) -> ProjectMemoryRead:
        memory = self.db.execute(
            select(ProjectMemory).where(ProjectMemory.project_id == project_id)
        ).scalar_one_or_none()
        if memory is None:
            return ProjectMemoryRead(project_id=project_id, reconstructed=False)

        last_run = None
        if memory.last_run_id is not None:
            row = self.db.get(ProcessingRun, memory.last_run_id)
            if row is not None:
                last_run = ProcessingRunRead.model_validate(row)
        return ProjectMemoryRead(
            project_id=project_id,
            reconstructed=True,
            version=memory.version,
            summary=memory.summary,
            stats=dict(memory.stats or {}),
            generated_at=memory.generated_at,
            last_run_id=memory.last_run_id,
            last_run=last_run,
        )

    # -- claims --------------------------------------------------------
    def list_claims(
        self,
        project_id: uuid.UUID,
        *,
        claim_type: ClaimType | None = None,
        status: ClaimStatus | None = None,
        critical: bool | None = None,
        entity: str | None = None,
        search: str | None = None,
        order: str = "recent",
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ClaimSummary], int]:
        filters = [Claim.project_id == project_id]
        if claim_type is not None:
            filters.append(Claim.claim_type == claim_type)
        if status is not None:
            filters.append(Claim.status == status)
        if critical is not None:
            filters.append(Claim.critical.is_(critical))
        if entity:
            filters.append(Claim.entity.ilike(f"%{entity}%"))
        if search:
            filters.append(Claim.text.ilike(f"%{search}%"))

        total = self.db.execute(
            select(func.count()).select_from(Claim).where(*filters)
        ).scalar_one()

        source_date = _source_date_subquery().label("source_date")
        statement = select(Claim, source_date).where(*filters)
        if order == "timeline":
            statement = statement.order_by(source_date.asc().nulls_last(), Claim.created_at.asc())
        elif order == "oldest":
            statement = statement.order_by(Claim.created_at.asc(), Claim.id.asc())
        else:
            statement = statement.order_by(Claim.created_at.desc(), Claim.id.desc())
        rows = self.db.execute(
            statement.limit(page_size).offset((page - 1) * page_size)
        ).all()

        counts = self._evidence_counts([row[0].id for row in rows])
        items = [
            ClaimSummary.model_validate(
                _claim_payload(claim, counts.get(claim.id, 0), evidence_date)
            )
            for claim, evidence_date in rows
        ]
        return items, int(total)

    def claim_counts(self, project_id: uuid.UUID) -> tuple[dict[str, int], dict[str, int]]:
        status_rows = self.db.execute(
            select(Claim.status, func.count())
            .where(Claim.project_id == project_id)
            .group_by(Claim.status)
        ).all()
        type_rows = self.db.execute(
            select(Claim.claim_type, func.count())
            .where(Claim.project_id == project_id)
            .group_by(Claim.claim_type)
        ).all()
        return (
            {_value(key): int(count) for key, count in status_rows},
            {_value(key): int(count) for key, count in type_rows},
        )

    def get_claim(self, project_id: uuid.UUID, claim_id: uuid.UUID) -> Claim:
        claim = self.db.get(Claim, claim_id)
        if claim is None or claim.project_id != project_id:
            raise NotFoundError("Claim not found.")
        return claim

    def claim_detail(self, claim: Claim) -> ClaimDetail:
        counts = self._evidence_counts([claim.id])
        payload = _claim_payload(claim, counts.get(claim.id, 0), self._source_date(claim.id))
        review = ReviewService(self.db)
        return ClaimDetail.model_validate(
            {
                **payload,
                "evidence": self.evidence_refs(claim.id),
                "verifications": [
                    VerificationRead.model_validate(row) for row in self._verifications(claim.id)
                ],
                "history": [
                    ClaimHistoryRead.model_validate(row) for row in self._history(claim.id)
                ],
                "conflicts": self.conflicts_for_claim(claim.id),
                # --- Phase 4 review context -------------------------------
                "review_status": machine.review_status_label(claim.status),
                "revision_number": claim.revision_number,
                "allowed_transitions": machine.allowed_transitions(claim.status),
                "revisions": review.revisions(claim.id),
                "decisions": review.decisions(claim.id),
            }
        )

    # -- evidence ------------------------------------------------------
    def evidence_refs(self, claim_id: uuid.UUID) -> list[EvidenceRef]:
        rows = self.db.execute(
            select(Evidence, Source, EvidenceSpan)
            .join(Source, Source.id == Evidence.source_id)
            .outerjoin(EvidenceSpan, EvidenceSpan.id == Evidence.span_id)
            .where(Evidence.claim_id == claim_id)
            .order_by(Evidence.created_at)
        ).all()
        refs: list[EvidenceRef] = []
        for evidence, source, span in rows:
            refs.append(
                EvidenceRef(
                    id=evidence.id,
                    source_id=source.id,
                    span_id=evidence.span_id,
                    source_name=source.source_name,
                    source_type=source.source_type,
                    source_location=evidence.source_location,
                    start_offset=evidence.start_offset,
                    end_offset=evidence.end_offset,
                    supporting_quote=evidence.supporting_quote,
                    access_label=source.access_label,
                    source_date=source.created_at_source or source.created_at,
                    author=source.author,
                    meta=dict(span.meta or {}) if span is not None else {},
                )
            )
        return refs

    # -- conflicts -----------------------------------------------------
    def list_conflicts(
        self,
        project_id: uuid.UUID,
        *,
        status: ConflictStatus | None = None,
        kind: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ConflictSummary], int]:
        filters = [Conflict.project_id == project_id]
        if status is not None:
            filters.append(Conflict.status == status)
        if kind is not None:
            filters.append(Conflict.kind == kind)

        total = self.db.execute(
            select(func.count()).select_from(Conflict).where(*filters)
        ).scalar_one()
        rows = list(
            self.db.execute(
                select(Conflict)
                .where(*filters)
                .order_by(Conflict.created_at.desc(), Conflict.id.desc())
                .limit(page_size)
                .offset((page - 1) * page_size)
            ).scalars().all()
        )
        return [self.conflict_summary(row) for row in rows], int(total)

    def conflicts_for_claim(self, claim_id: uuid.UUID) -> list[ConflictSummary]:
        rows = list(
            self.db.execute(
                select(Conflict)
                .join(ConflictClaim, ConflictClaim.conflict_id == Conflict.id)
                .where(ConflictClaim.claim_id == claim_id)
                .order_by(Conflict.created_at.desc())
            ).scalars().all()
        )
        return [self.conflict_summary(row) for row in rows]

    def get_conflict(self, project_id: uuid.UUID, conflict_id: uuid.UUID) -> Conflict:
        conflict = self.db.get(Conflict, conflict_id)
        if conflict is None or conflict.project_id != project_id:
            raise NotFoundError("Conflict not found.")
        return conflict

    # -- questions and freshness --------------------------------------
    def list_questions(
        self,
        project_id: uuid.UUID,
        *,
        status: OpenQuestionStatus | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[OpenQuestionRead], int]:
        filters = [OpenQuestion.project_id == project_id]
        if status is not None:
            filters.append(OpenQuestion.status == status)
        total = self.db.execute(
            select(func.count()).select_from(OpenQuestion).where(*filters)
        ).scalar_one()
        rows = list(
            self.db.execute(
                select(OpenQuestion)
                .where(*filters)
                .order_by(OpenQuestion.created_at.desc())
                .limit(page_size)
                .offset((page - 1) * page_size)
            ).scalars().all()
        )
        return [OpenQuestionRead.model_validate(row) for row in rows], int(total)

    def stale_sources(self, project_id: uuid.UUID) -> list[StaleSourceRead]:
        rows = list(
            self.db.execute(
                select(Source)
                .where(
                    Source.project_id == project_id,
                    Source.freshness != FreshnessStatus.CURRENT,
                )
                .order_by(Source.created_at_source.desc().nulls_last())
            ).scalars().all()
        )
        return [
            StaleSourceRead(
                id=row.id,
                source_name=row.source_name,
                source_type=row.source_type,
                author=row.author,
                created_at_source=row.created_at_source,
                freshness=row.freshness,
                freshness_checked_at=row.freshness_checked_at,
                warnings=[item for item in (row.warnings or []) if isinstance(item, dict)],
            )
            for row in rows
        ]

    def uncertainty_centre(self, project_id: uuid.UUID) -> UncertaintyResponse:
        unsupported = list(
            self.db.execute(
                select(Claim)
                .where(Claim.project_id == project_id, Claim.status.in_(_UNRESOLVED_STATUSES))
                .order_by(Claim.critical.desc(), Claim.created_at.desc())
                .limit(200)
            ).scalars().all()
        )
        counts = self._evidence_counts([row.id for row in unsupported])
        dates = self._source_dates([row.id for row in unsupported])
        questions, _ = self.list_questions(project_id, status=OpenQuestionStatus.OPEN, page_size=200)
        return UncertaintyResponse(
            unsupported_claims=[
                ClaimSummary.model_validate(
                    _claim_payload(row, counts.get(row.id, 0), dates.get(row.id))
                )
                for row in unsupported
            ],
            open_questions=questions,
            stale_sources=self.stale_sources(project_id),
        )

    # -- processing runs ----------------------------------------------
    def list_runs(
        self, project_id: uuid.UUID, *, page: int = 1, page_size: int = 20
    ) -> tuple[list[ProcessingRunRead], int]:
        total = self.db.execute(
            select(func.count()).select_from(ProcessingRun).where(
                ProcessingRun.project_id == project_id
            )
        ).scalar_one()
        rows = list(
            self.db.execute(
                select(ProcessingRun)
                .where(ProcessingRun.project_id == project_id)
                .order_by(ProcessingRun.created_at.desc())
                .limit(page_size)
                .offset((page - 1) * page_size)
            ).scalars().all()
        )
        return [ProcessingRunRead.model_validate(row) for row in rows], int(total)

    # -- human actions -------------------------------------------------
    def review_claim(
        self,
        claim: Claim,
        *,
        user: User,
        action: str,
        note: str | None,
    ) -> Claim:
        """Approve (→ *Verified*) or reject (→ *Uncertain*) a claim."""
        if action == "approve":
            if claim.status is ClaimStatus.VERIFIED:
                raise ConflictError("This claim is already approved.")
            if not self._evidence_counts([claim.id]).get(claim.id):
                raise ValidationAppError(
                    "A claim cannot be approved without traceable evidence."
                )
            if self._has_open_conflict(claim.id):
                raise ConflictError(
                    "Resolve the open conflict for this claim before approving it."
                )
            from_status = claim.status
            claim.status = ClaimStatus.VERIFIED
            claim.verified_by_id = user.id
            claim.verified_at = _now()
            claim.reviewed_at = _now()
            claim.review_note = note
            history_action = "approved"
        else:
            from_status = claim.status
            claim.status = ClaimStatus.UNCERTAIN
            claim.verified_by_id = None
            claim.verified_at = None
            claim.reviewed_at = _now()
            claim.review_note = note
            history_action = "rejected"

        self.db.add(
            ClaimHistory(
                claim_id=claim.id,
                actor_id=user.id,
                action=history_action,
                from_status=from_status,
                to_status=claim.status,
                note=note,
            )
        )
        project = self.db.get(Project, claim.project_id)
        self.db.add(AuditLog(
            user_id=user.id,
            workspace_id=project.workspace_id if project else None,
            action=f"claim_{history_action}",
            resource_type="claim",
            resource_id=claim.id,
            meta={"note": note or "", "claim_status": claim.status.value},
        ))
        self.db.commit()
        return claim

    def verify_claim(
        self, claim: Claim, *, provider: LLMProvider
    ) -> tuple[Claim, Verification | None]:
        """Re-run the Verifier. Never approves a claim, never undoes a review."""
        if claim.status is ClaimStatus.VERIFIED:
            raise ConflictError(
                "This claim has been approved by a human reviewer. "
                "An automatic re-verification cannot overwrite that decision."
            )

        chunks = self._chunks_for_claim(claim)
        candidate = ExtractedClaim(
            local_id=claim.id,
            project_id=claim.project_id,
            text=claim.text,
            claim_type=claim.claim_type,
            entity=claim.entity,
        )
        result, error = VerifierAgent(provider).verify(claim=candidate, chunks=chunks)
        if error is not None:
            raise UpstreamError(
                "The Verifier could not complete.", code=error.code
            )
        if result is None:  # pragma: no cover - defensive
            raise UpstreamError("The Verifier returned no verdict.", code="ai_empty_response")

        from_status = claim.status
        claim.status = status_from_verification(result.verdict, bool(result.contradicted_by))

        row = Verification(
            claim_id=claim.id,
            verdict=result.verdict,
            supporting_quote=result.supporting_quote,
            quote_validated=result.quote_validated,
            contradicted_by=[str(item) for item in result.contradicted_by],
            explanation=result.explanation,
            confidence=result.confidence,
            model_name=result.model_name,
        )
        self.db.add(row)
        self.db.add(
            ClaimHistory(
                claim_id=claim.id,
                action="verified",
                from_status=from_status,
                to_status=claim.status,
                note=f"Verifier verdict: {result.verdict.value}.",
                meta={"quote_validated": result.quote_validated, "manual": True},
            )
        )
        self.db.commit()
        self.db.refresh(row)
        return claim, row

    def resolve_conflict(
        self,
        conflict: Conflict,
        *,
        user: User,
        action: str,
        note: str,
        chosen_claim_id: uuid.UUID | None = None,
    ) -> Conflict:
        """Record a reviewer's decision; the conflict row is never deleted."""
        if conflict.status is not ConflictStatus.OPEN:
            raise ConflictError("This conflict has already been decided.")

        linked = [
            link.claim_id
            for link in self.db.execute(
                select(ConflictClaim).where(ConflictClaim.conflict_id == conflict.id)
            ).scalars().all()
        ]
        if chosen_claim_id is not None and chosen_claim_id not in linked:
            raise ValidationAppError("The chosen claim is not part of this conflict.")

        if action == "resolve" and chosen_claim_id is not None:
            for claim_id in linked:
                claim = self.db.get(Claim, claim_id)
                if claim is None:  # pragma: no cover - deleted mid-review
                    continue
                if claim_id == chosen_claim_id:
                    from_status, claim.status = claim.status, ClaimStatus.SUPPORTED
                else:
                    from_status, claim.status = claim.status, ClaimStatus.UNCERTAIN
                self.db.add(
                    ClaimHistory(
                        claim_id=claim.id,
                        actor_id=user.id,
                        action="conflict_resolved",
                        from_status=from_status,
                        to_status=claim.status,
                        note=note,
                        meta={"conflict_id": str(conflict.id)},
                    )
                )

        conflict.status = (
            ConflictStatus.RESOLVED if action == "resolve" else ConflictStatus.DISMISSED
        )
        conflict.resolution_note = note
        conflict.resolved_by_id = user.id
        conflict.resolved_at = _now()
        self.db.commit()
        return conflict

    # -- handover ------------------------------------------------------
    def generate_handover(
        self, project: Project, *, user: User, provider: LLMProvider
    ) -> HandoverDocument:
        handover_input = approved_claim_handles(self.db, project.id)
        handover_input.questions = [
            row.question
            for row in self.db.execute(
                select(OpenQuestion)
                .where(
                    OpenQuestion.project_id == project.id,
                    OpenQuestion.status == OpenQuestionStatus.OPEN,
                )
                .order_by(OpenQuestion.created_at)
            ).scalars().all()
        ]

        validation, error = HandoverWriterAgent(provider).write(
            project_name=project.name, handover_input=handover_input
        )
        if error is not None:
            raise UpstreamError("The Handover Writer could not complete.", code=error.code)
        if validation is None:  # pragma: no cover - defensive
            raise UpstreamError("The Handover Writer returned no document.")

        document = HandoverDocument(
            project_id=project.id,
            generated_by_id=user.id,
            status=(
                HandoverStatus.VALIDATED
                if not validation.errors
                else HandoverStatus.GENERATED
            ),
            sections=[
                {
                    "key": section.key,
                    "title": section.title,
                    "statements": [
                        {
                            "statement_id": item.statement_id,
                            "text": item.text,
                            "statement_type": item.statement_type,
                            "claim_ids": [str(cid) for cid in item.claim_ids],
                            "claim_revisions": dict(item.claim_revisions or {}),
                        }
                        for item in section.statements
                    ],
                    "not_established": section.not_established,
                    "placeholder": section.placeholder,
                }
                for section in validation.sections
            ],
            claim_ids=[str(claim_id) for claim_id in validation.claim_ids],
            validation_errors=[dict(item) for item in validation.errors],
            summary=validation.summary,
            model_name=getattr(provider, "model", None),
            meta={
                "approved_claim_count": len(handover_input.claims),
                "claim_revisions": dict(validation.claim_revisions),
            },
        )
        self.db.add(document)
        self.db.commit()
        self.db.refresh(document)
        return document

    def latest_handover(self, project_id: uuid.UUID) -> HandoverDocument | None:
        return self.db.execute(
            select(HandoverDocument)
            .where(HandoverDocument.project_id == project_id)
            .order_by(HandoverDocument.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()

    # -- helpers -------------------------------------------------------
    def _evidence_counts(self, claim_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        if not claim_ids:
            return {}
        rows = self.db.execute(
            select(Evidence.claim_id, func.count())
            .where(Evidence.claim_id.in_(claim_ids))
            .group_by(Evidence.claim_id)
        ).all()
        return {claim_id: int(count) for claim_id, count in rows}

    def _source_dates(self, claim_ids: list[uuid.UUID]) -> dict[uuid.UUID, datetime | None]:
        if not claim_ids:
            return {}
        rows = self.db.execute(
            select(
                Evidence.claim_id,
                func.min(func.coalesce(Source.created_at_source, Source.created_at)),
            )
            .join(Source, Source.id == Evidence.source_id)
            .where(Evidence.claim_id.in_(claim_ids))
            .group_by(Evidence.claim_id)
        ).all()
        return {claim_id: value for claim_id, value in rows}

    def _source_date(self, claim_id: uuid.UUID) -> datetime | None:
        return self._source_dates([claim_id]).get(claim_id)

    def _verifications(self, claim_id: uuid.UUID) -> list[Verification]:
        return list(
            self.db.execute(
                select(Verification)
                .where(Verification.claim_id == claim_id)
                .order_by(Verification.created_at.desc())
            ).scalars().all()
        )

    def _history(self, claim_id: uuid.UUID) -> list[ClaimHistory]:
        return list(
            self.db.execute(
                select(ClaimHistory)
                .where(ClaimHistory.claim_id == claim_id)
                .order_by(ClaimHistory.created_at.desc(), ClaimHistory.id.desc())
            ).scalars().all()
        )

    def _has_open_conflict(self, claim_id: uuid.UUID) -> bool:
        return bool(
            self.db.execute(
                select(func.count())
                .select_from(ConflictClaim)
                .join(Conflict, Conflict.id == ConflictClaim.conflict_id)
                .where(
                    ConflictClaim.claim_id == claim_id,
                    Conflict.status == ConflictStatus.OPEN,
                )
            ).scalar_one()
        )

    def conflict_summary(self, conflict: Conflict) -> ConflictSummary:
        """Serialise one conflict together with the claims that disagree about it."""
        claim_ids = [
            link.claim_id
            for link in self.db.execute(
                select(ConflictClaim).where(ConflictClaim.conflict_id == conflict.id)
            ).scalars().all()
        ]
        claims = list(
            self.db.execute(select(Claim).where(Claim.id.in_(claim_ids))).scalars().all()
        )
        counts = self._evidence_counts([claim.id for claim in claims])
        dates = self._source_dates([claim.id for claim in claims])
        return ConflictSummary.model_validate(
            {
                **_orm_payload(conflict),
                "claims": [
                    _claim_payload(claim, counts.get(claim.id, 0), dates.get(claim.id))
                    for claim in claims
                ],
            }
        )

    def conflict_detail(self, conflict: Conflict) -> ConflictDetail:
        """Serialise a contradiction for the Conflict Resolution Centre (§6).

        Both sides keep their own evidence: nothing is deleted or hidden when a
        reviewer decides who wins. Restricted source text is withheld — the
        reviewer sees that evidence exists without seeing protected content.
        """
        claim_ids = [
            link.claim_id
            for link in self.db.execute(
                select(ConflictClaim).where(ConflictClaim.conflict_id == conflict.id)
            ).scalars().all()
        ]
        claims = list(
            self.db.execute(select(Claim).where(Claim.id.in_(claim_ids))).scalars().all()
        ) if claim_ids else []
        order = {claim_id: index for index, claim_id in enumerate(claim_ids)}
        claims.sort(key=lambda row: order.get(row.id, 0))
        dates = self._source_dates([claim.id for claim in claims])
        meta = dict(conflict.resolution_meta or {})

        payload: list[ConflictClaimRead] = []
        for claim in claims:
            evidence = [
                ref.model_dump(mode="json")
                for ref in self.evidence_refs(claim.id)
                if ref.access_label is not AccessLabel.RESTRICTED
            ]
            payload.append(
                ConflictClaimRead(
                    id=claim.id,
                    text=claim.text,
                    claim_type=claim.claim_type,
                    entity=claim.entity,
                    status=claim.status,
                    author=claim.author,
                    confidence=claim.confidence,
                    created_at=claim.created_at,
                    source_date=dates.get(claim.id),
                    evidence=evidence,
                )
            )

        return ConflictDetail.model_validate(
            {
                **_orm_payload(conflict),
                "resolution_label": meta.get("resolution_label"),
                "could_be_temporal_change": bool(
                    meta.get(
                        "could_be_temporal_change",
                        conflict.kind == "changed_over_time",
                    )
                ),
                "claims": payload,
            }
        )

    def _chunks_for_claim(self, claim: Claim) -> list[EvidenceChunk]:
        refs = self.evidence_refs(claim.id)
        chunks: list[EvidenceChunk] = []
        for index, ref in enumerate(refs):
            if ref.span_id is None or not ref.supporting_quote:
                continue
            chunks.append(
                EvidenceChunk(
                    label=f"S{index + 1}",
                    span_id=ref.span_id,
                    source_id=ref.source_id,
                    source_name=ref.source_name or "",
                    source_type=_value(ref.source_type),
                    location=ref.source_location or "",
                    author=ref.author,
                    source_date=ref.source_date,
                    start_offset=ref.start_offset,
                    end_offset=ref.end_offset,
                    text=ref.supporting_quote,
                    metadata=dict(ref.metadata or {}),
                )
            )
        return chunks


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------
def _source_date_subquery():
    """Earliest evidence source date for a claim (for the decision timeline)."""
    return (
        select(func.min(func.coalesce(Source.created_at_source, Source.created_at)))
        .select_from(Evidence)
        .join(Source, Source.id == Evidence.source_id)
        .where(Evidence.claim_id == Claim.id)
        .correlate(Claim)
        .scalar_subquery()
    )


def _value(item: object) -> str:
    return item.value if hasattr(item, "value") else str(item)


def _orm_payload(row: object) -> dict:
    """Field values of an ORM row keyed by mapped attribute name.

    The mapper's attribute keys are used (not the physical column names) so a
    column that is deliberately named differently on the database — e.g.
    ``resolution_metadata`` for the Python attribute ``resolution_meta`` — is
    still serialised under its attribute name.
    """
    mapper = sa_inspect(row).mapper
    return {attr.key: getattr(row, attr.key) for attr in mapper.column_attrs}


def _claim_payload(claim: Claim, evidence_count: int, source_date: datetime | None) -> dict:
    return {
        **_orm_payload(claim),
        "evidence_count": evidence_count,
        "source_date": source_date,
    }
