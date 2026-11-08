"""Human review, editing and the approval engine (Phase 4 §4, §5, §7).

Everything in this module is a **human** action. Nothing here reads a model
confidence score to decide anything: an approval is an explicit, attributed
reviewer decision recorded against one exact claim revision.

Guarantees enforced here rather than in the UI:

* every transition goes through :mod:`app.services.claim_state_machine`;
* a claim cannot be approved without traceable, still-present evidence;
* a claim with an undecided conflict cannot be approved;
* a materially edited claim loses its approval and must be verified and
  approved again;
* every action is recorded in ``claim_history``, ``claim_decisions`` and the
  workspace audit trail, and the whole operation is one transaction.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, ForbiddenError, ValidationAppError
from app.models.audit import AuditLog
from app.models.claim import Claim
from app.models.claim_history import ClaimHistory
from app.models.claim_revision import ClaimDecision, ClaimRevision
from app.models.conflict import Conflict, ConflictClaim
from app.models.enums import (
    AWAITING_REVIEW_STATUSES,
    ClaimStatus,
    ClaimType,
    ConflictStatus,
    ReviewDecision,
    WorkspaceRole,
)
from app.models.evidence import Evidence
from app.models.project import Project
from app.models.source import Source
from app.models.user import User
from app.models.verification import Verification
from app.services import claim_state_machine as machine

#: Roles allowed to record a human review decision.
REVIEWER_ROLES: frozenset[WorkspaceRole] = frozenset(
    {WorkspaceRole.OWNER, WorkspaceRole.ADMIN}
)

_NOT_ESTABLISHED = "Information not established from the available evidence."


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _normalise(text: str) -> str:
    return " ".join(text.split())


class ReviewService:
    """Transactional human review of claims."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # -- revisions -----------------------------------------------------
    def ensure_revision(self, claim: Claim) -> ClaimRevision:
        """Return the row for the claim's *current* revision.

        Claims persisted before Phase 4 (or created directly by the workflow)
        have no revision rows; the original statement is materialised as
        revision 1 the first time a reviewer touches the claim.
        """
        existing = self.db.execute(
            select(ClaimRevision)
            .where(
                ClaimRevision.claim_id == claim.id,
                ClaimRevision.revision_number == claim.revision_number,
            )
            .limit(1)
        ).scalar_one_or_none()
        if existing is not None:
            return existing

        revision = ClaimRevision(
            claim_id=claim.id,
            revision_number=claim.revision_number,
            text=claim.text,
            claim_type=claim.claim_type,
            entity=claim.entity,
            note="Original statement as extracted.",
            created_by_id=None,
            is_material=False,
            verification_required=False,
        )
        self.db.add(revision)
        self.db.flush()
        return revision

    def revisions(self, claim_id: uuid.UUID) -> list[ClaimRevision]:
        return list(
            self.db.execute(
                select(ClaimRevision)
                .where(ClaimRevision.claim_id == claim_id)
                .order_by(ClaimRevision.revision_number)
            ).scalars().all()
        )

    def decisions(self, claim_id: uuid.UUID) -> list[ClaimDecision]:
        return list(
            self.db.execute(
                select(ClaimDecision)
                .where(ClaimDecision.claim_id == claim_id)
                .order_by(ClaimDecision.created_at.desc())
            ).scalars().all()
        )

    def current_revision_id(self, claim: Claim) -> uuid.UUID | None:
        return self.ensure_revision(claim).id

    # -- editing -------------------------------------------------------
    def edit_claim(
        self,
        claim: Claim,
        *,
        user: User,
        text: str | None = None,
        claim_type: ClaimType | None = None,
        entity: str | None = None,
        note: str | None = None,
    ) -> ClaimRevision:
        """Apply a reviewer's correction as a **new** claim revision.

        A material edit (statement or category) never inherits the previous
        evidence verification: the new revision is flagged
        ``verification_required`` and the claim drops to *Pending Review*.
        """
        if not note or len(note.strip()) < 4:
            raise ValidationAppError(
                "Editing a claim requires an explanation for the change.",
                code="edit_note_required",
            )

        previous = self.ensure_revision(claim)
        new_text = _normalise(text) if text is not None else claim.text
        new_type = claim_type or claim.claim_type
        new_entity = entity if entity is not None else claim.entity

        if not new_text:
            raise ValidationAppError("A claim cannot be edited to an empty statement.")

        material = new_text != claim.text or new_type != claim.claim_type
        if not material and new_entity == claim.entity:
            raise ValidationAppError(
                "Nothing changed. Edit the statement, category or entity.",
                code="edit_no_change",
            )

        from_status = claim.status
        claim.text = new_text
        claim.claim_type = new_type
        claim.entity = new_entity
        claim.revision_number += 1

        revision = ClaimRevision(
            claim_id=claim.id,
            revision_number=claim.revision_number,
            text=new_text,
            claim_type=new_type,
            entity=new_entity,
            note=note.strip(),
            created_by_id=user.id,
            is_material=material,
            # A materially edited statement must be verified again.
            verification_required=material,
        )

        # An edited claim may never keep its old approval.
        if material:
            machine.assert_transition(from_status, ClaimStatus.PENDING_REVIEW, action="edit")
            claim.status = ClaimStatus.PENDING_REVIEW
            claim.verified_by_id = None
            claim.verified_at = None
        claim.reviewed_at = _now()
        claim.review_note = note.strip()

        self.db.add(revision)
        self.db.add(
            ClaimHistory(
                claim_id=claim.id,
                actor_id=user.id,
                action="edited",
                from_status=from_status,
                to_status=claim.status,
                note=note.strip(),
                meta={
                    "revision_number": claim.revision_number,
                    "material": material,
                    "previous_revision": previous.revision_number,
                },
            )
        )
        self._audit(
            claim,
            user=user,
            action="claim_edited",
            metadata={
                "revision_number": claim.revision_number,
                "material": material,
                "from_status": from_status.value,
                "to_status": claim.status.value,
            },
        )
        self.db.commit()
        self.db.refresh(revision)
        return revision

    # -- decisions -----------------------------------------------------
    def approve(
        self,
        claim: Claim,
        *,
        user: User,
        role: WorkspaceRole,
        explanation: str | None = None,
    ) -> ClaimDecision:
        """Approve a claim. Only this method may produce an approved claim."""
        self._require_reviewer(role)
        revision = self.ensure_revision(claim)
        self._assert_approvable(claim, revision)

        from_status = claim.status
        machine.assert_transition(from_status, ClaimStatus.VERIFIED, action="approve")
        claim.status = ClaimStatus.VERIFIED
        claim.verified_by_id = user.id
        claim.verified_at = _now()
        claim.reviewed_at = _now()
        claim.review_note = explanation

        return self._record(
            claim,
            revision=revision,
            user=user,
            decision=ReviewDecision.APPROVE,
            explanation=explanation,
            from_status=from_status,
            to_status=claim.status,
            history_action="approved",
            audit_action="claim_approved",
        )

    def reject(
        self,
        claim: Claim,
        *,
        user: User,
        role: WorkspaceRole,
        explanation: str | None = None,
    ) -> ClaimDecision:
        self._require_reviewer(role)
        revision = self.ensure_revision(claim)
        from_status = claim.status
        machine.assert_transition(from_status, ClaimStatus.REJECTED, action="reject")

        claim.status = ClaimStatus.REJECTED
        claim.verified_by_id = None
        claim.verified_at = None
        claim.reviewed_at = _now()
        claim.review_note = explanation

        return self._record(
            claim,
            revision=revision,
            user=user,
            decision=ReviewDecision.REJECT,
            explanation=explanation,
            from_status=from_status,
            to_status=claim.status,
            history_action="rejected",
            audit_action="claim_rejected",
        )

    def request_clarification(
        self,
        claim: Claim,
        *,
        user: User,
        role: WorkspaceRole,
        explanation: str | None = None,
        request_evidence: bool = False,
    ) -> ClaimDecision:
        """Ask for clarification or additional evidence; the claim leaves review."""
        self._require_reviewer(role)
        if not explanation or len(explanation.strip()) < 4:
            raise ValidationAppError(
                "Explain what clarification or evidence is required.",
                code="clarification_note_required",
            )
        revision = self.ensure_revision(claim)
        from_status = claim.status
        machine.assert_transition(
            from_status, ClaimStatus.NEEDS_CLARIFICATION, action="request clarification for"
        )

        claim.status = ClaimStatus.NEEDS_CLARIFICATION
        claim.reviewed_at = _now()
        claim.review_note = explanation

        decision = (
            ReviewDecision.REQUEST_EVIDENCE
            if request_evidence
            else ReviewDecision.CLARIFICATION
        )
        return self._record(
            claim,
            revision=revision,
            user=user,
            decision=decision,
            explanation=explanation,
            from_status=from_status,
            to_status=claim.status,
            history_action=(
                "additional_evidence_requested" if request_evidence else "clarification_requested"
            ),
            audit_action=(
                "claim_evidence_requested" if request_evidence else "claim_clarification_requested"
            ),
        )

    # -- policy checks -------------------------------------------------
    def _require_reviewer(self, role: WorkspaceRole) -> None:
        if role not in REVIEWER_ROLES:
            raise ForbiddenError(
                "Only a workspace owner or admin may approve, reject or "
                "request clarification for a claim."
            )

    def _assert_approvable(self, claim: Claim, revision: ClaimRevision) -> None:
        if claim.status is ClaimStatus.REJECTED:
            raise ConflictError(
                "This claim has been rejected. Re-open it for review before approving it.",
                details={"from_status": claim.status.value},
            )
        if self.open_conflict_ids(claim.id):
            raise ConflictError(
                "This claim is part of an undecided conflict. Resolve the conflict "
                "before approving the claim.",
                details={"conflict_ids": [str(item) for item in self.open_conflict_ids(claim.id)]},
            )
        evidence = self.accessible_evidence(claim.id)
        if not evidence:
            raise ValidationAppError(
                "A claim cannot be approved without traceable evidence that is "
                "still available in the project.",
                code="evidence_required",
            )
        if revision.verification_required and not self._verified_since(revision):
            raise ValidationAppError(
                "This revision was edited and must be verified before it can be approved.",
                code="verification_required",
            )

    # -- lookups -------------------------------------------------------
    def accessible_evidence(self, claim_id: uuid.UUID) -> list[tuple[Evidence, Source]]:
        """Evidence rows whose source still exists (i.e. is still accessible)."""
        rows = self.db.execute(
            select(Evidence, Source)
            .join(Source, Source.id == Evidence.source_id)
            .where(Evidence.claim_id == claim_id)
        ).all()
        return [(evidence, source) for evidence, source in rows if source is not None]

    def open_conflict_ids(self, claim_id: uuid.UUID) -> list[uuid.UUID]:
        return list(
            self.db.execute(
                select(Conflict.id)
                .join(ConflictClaim, ConflictClaim.conflict_id == Conflict.id)
                .where(
                    ConflictClaim.claim_id == claim_id,
                    Conflict.status == ConflictStatus.OPEN,
                )
            ).scalars().all()
        )

    def _verified_since(self, revision: ClaimRevision) -> bool:
        count = self.db.execute(
            select(func.count())
            .select_from(Verification)
            .where(
                Verification.claim_id == revision.claim_id,
                Verification.created_at >= revision.created_at,
            )
        ).scalar_one()
        return bool(count)

    # -- plumbing ------------------------------------------------------
    def _record(
        self,
        claim: Claim,
        *,
        revision: ClaimRevision,
        user: User,
        decision: ReviewDecision,
        explanation: str | None,
        from_status: ClaimStatus,
        to_status: ClaimStatus,
        history_action: str,
        audit_action: str,
    ) -> ClaimDecision:
        row = ClaimDecision(
            project_id=claim.project_id,
            claim_id=claim.id,
            claim_revision_id=revision.id,
            reviewer_id=user.id,
            decision=decision,
            explanation=explanation,
            from_status=from_status.value,
            to_status=to_status.value,
            meta={"revision_number": revision.revision_number},
        )
        self.db.add(row)
        self.db.add(
            ClaimHistory(
                claim_id=claim.id,
                actor_id=user.id,
                action=history_action,
                from_status=from_status,
                to_status=to_status,
                note=explanation,
                meta={
                    "revision_number": revision.revision_number,
                    "claim_revision_id": str(revision.id),
                },
            )
        )
        self._audit(
            claim,
            user=user,
            action=audit_action,
            metadata={
                "decision": decision.value,
                "revision_number": revision.revision_number,
                "from_status": from_status.value,
                "to_status": to_status.value,
            },
        )
        self.db.commit()
        self.db.refresh(row)
        return row

    def _audit(
        self, claim: Claim, *, user: User, action: str, metadata: dict
    ) -> None:
        project = self.db.get(Project, claim.project_id)
        self.db.add(
            AuditLog(
                user_id=user.id,
                workspace_id=project.workspace_id if project else None,
                action=action,
                resource_type="claim",
                resource_id=claim.id,
                meta={"project_id": str(claim.project_id), **metadata},
            )
        )


# ---------------------------------------------------------------------------
# Review-queue helpers
# ---------------------------------------------------------------------------
#: Filter aliases accepted by ``GET /projects/{id}/review-queue``.
QUEUE_FILTERS: dict[str, tuple[ClaimStatus, ...]] = {
    "pending": AWAITING_REVIEW_STATUSES,
    "supported": (ClaimStatus.SUPPORTED,),
    "uncertain": (ClaimStatus.UNCERTAIN,),
    "conflict": (ClaimStatus.CONFLICT,),
    "resolved": (ClaimStatus.VERIFIED, ClaimStatus.REJECTED),
    "approved": (ClaimStatus.VERIFIED,),
    "rejected": (ClaimStatus.REJECTED,),
    "clarification": (ClaimStatus.NEEDS_CLARIFICATION,),
}


def statuses_for_filter(name: str | None) -> tuple[ClaimStatus, ...] | None:
    """Map a queue filter name to the claim statuses it selects."""
    if not name:
        return None
    if name == "critical":
        return None
    statuses = QUEUE_FILTERS.get(name.casefold())
    if statuses is not None:
        return statuses
    matched = next(
        (item for item in ClaimStatus if item.value.casefold() == name.casefold()), None
    )
    return (matched,) if matched is not None else None
