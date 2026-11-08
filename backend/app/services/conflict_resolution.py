"""Conflict Resolution Centre (Phase 4 §6).

The Conflict Centre never deletes contradictory evidence and never lets the
application pick a winner on its own. A reviewer chooses one of five outcomes and
explains the decision; the resolution is stored *alongside* the original claims.

A resolution that is merely "we need more information" leaves the conflict
**open**, so the affected claims still cannot be approved — an undecided
contradiction must never slip into an approved handover.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, ValidationAppError
from app.models.audit import AuditLog
from app.models.claim import Claim
from app.models.claim_history import ClaimHistory
from app.models.conflict import Conflict, ConflictClaim
from app.models.enums import ClaimStatus, ConflictResolution, ConflictStatus
from app.models.project import Project
from app.models.user import User

#: Human-facing labels for each option (used by the API and the export).
RESOLUTION_LABELS: dict[ConflictResolution, str] = {
    ConflictResolution.ACCEPT_A: "Claim A accepted",
    ConflictResolution.ACCEPT_B: "Claim B accepted",
    ConflictResolution.BOTH_VALID_OVER_TIME: "Both valid in different time periods",
    ConflictResolution.BOTH_REJECTED: "Both claims rejected",
    ConflictResolution.MORE_INFO_REQUIRED: "More information required",
    ConflictResolution.DISMISSED: "Not a contradiction (dismissed)",
}

#: Resolutions that put the affected claims into a claim status.
_CLAIM_OUTCOMES: dict[ConflictResolution, dict[str, ClaimStatus]] = {
    ConflictResolution.ACCEPT_A: {"chosen": ClaimStatus.SUPPORTED, "other": ClaimStatus.UNCERTAIN},
    ConflictResolution.ACCEPT_B: {"chosen": ClaimStatus.SUPPORTED, "other": ClaimStatus.UNCERTAIN},
    ConflictResolution.BOTH_REJECTED: {"chosen": ClaimStatus.REJECTED, "other": ClaimStatus.REJECTED},
    # Both statements are true of their own period: each keeps its own support.
    ConflictResolution.BOTH_VALID_OVER_TIME: {
        "chosen": ClaimStatus.SUPPORTED,
        "other": ClaimStatus.SUPPORTED,
    },
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ConflictCentreService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def linked_claims(self, conflict: Conflict) -> list[Claim]:
        claim_ids = [
            link.claim_id
            for link in self.db.execute(
                select(ConflictClaim).where(ConflictClaim.conflict_id == conflict.id)
            ).scalars().all()
        ]
        if not claim_ids:
            return []
        rows = list(
            self.db.execute(select(Claim).where(Claim.id.in_(claim_ids))).scalars().all()
        )
        order = {claim_id: index for index, claim_id in enumerate(claim_ids)}
        rows.sort(key=lambda row: order.get(row.id, 0))
        return rows

    def resolve(
        self,
        conflict: Conflict,
        *,
        user: User,
        resolution: ConflictResolution,
        note: str,
        chosen_claim_id: uuid.UUID | None = None,
    ) -> Conflict:
        """Record a reviewer's decision. Neither claims nor evidence are deleted."""
        if conflict.status is not ConflictStatus.OPEN and resolution is not ConflictResolution.DISMISSED:
            raise ConflictError("This conflict has already been decided.")
        if not note or len(note.strip()) < 4:
            raise ValidationAppError(
                "A resolution requires the reviewer's explanation.",
                code="resolution_note_required",
            )

        claims = self.linked_claims(conflict)
        claim_a = claims[0].id if claims else None
        claim_b = claims[1].id if len(claims) > 1 else None

        if resolution in (ConflictResolution.ACCEPT_A, ConflictResolution.ACCEPT_B):
            target = chosen_claim_id or (
                claim_a if resolution is ConflictResolution.ACCEPT_A else claim_b
            )
            if target is None or target not in {claim.id for claim in claims}:
                raise ValidationAppError(
                    "The accepted claim must be one of the claims in this conflict.",
                    code="chosen_claim_required",
                )
        else:
            target = None

        outcomes = _CLAIM_OUTCOMES.get(resolution)
        applied: dict[str, str] = {}
        if outcomes is not None:
            for claim in claims:
                if resolution in (ConflictResolution.ACCEPT_A, ConflictResolution.ACCEPT_B):
                    from_status, claim.status = claim.status, outcomes["chosen"] if claim.id == target else outcomes["other"]
                else:
                    from_status, claim.status = claim.status, outcomes["chosen"]
                applied[str(claim.id)] = claim.status.value
                self.db.add(
                    ClaimHistory(
                        claim_id=claim.id,
                        actor_id=user.id,
                        action="conflict_resolved",
                        from_status=from_status,
                        to_status=claim.status,
                        note=note.strip(),
                        meta={
                            "conflict_id": str(conflict.id),
                            "resolution": resolution.value,
                        },
                    )
                )

        conflict.resolution = resolution.value
        conflict.resolution_note = note.strip()
        conflict.resolution_meta = {
            "reviewer_id": str(user.id),
            "resolved_at": _now().isoformat(),
            "resolution": resolution.value,
            "resolution_label": RESOLUTION_LABELS[resolution],
            "claim_a_id": str(claim_a) if claim_a else None,
            "claim_b_id": str(claim_b) if claim_b else None,
            "accepted_claim_id": str(target) if target else None,
            "applied_claim_statuses": applied,
            "could_be_temporal_change": conflict.kind == "changed_over_time",
        }
        conflict.resolved_by_id = user.id
        conflict.resolved_at = _now()
        if resolution is ConflictResolution.MORE_INFO_REQUIRED:
            # Still undecided: the claims must remain blocked from approval.
            pass
        else:
            conflict.status = (
                ConflictStatus.DISMISSED
                if resolution is ConflictResolution.DISMISSED
                else ConflictStatus.RESOLVED
            )

        project = self.db.get(Project, conflict.project_id)
        self.db.add(
            AuditLog(
                user_id=user.id,
                workspace_id=project.workspace_id if project else None,
                action="conflict_resolved",
                resource_type="conflict",
                resource_id=conflict.id,
                meta={
                    "project_id": str(conflict.project_id),
                    "resolution": resolution.value,
                    "note": note.strip(),
                    "status": conflict.status.value,
                },
            )
        )
        self.db.commit()
        self.db.refresh(conflict)
        return conflict
