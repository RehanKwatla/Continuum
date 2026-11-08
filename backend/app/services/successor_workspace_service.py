"""Successor readiness workspace (§4).

Builds the guided, section-by-section view a successor reads first. Every
section is assembled from **approved** claims, and every statement links back to
its supporting source evidence. Restricted source material is never included:
evidence references are resolved through the same access-aware index the
handover exporter uses.

The workspace deliberately does not invent content. Where a section has no
approved knowledge it says so, and points at the recorded missing-knowledge
gap rather than filling the space.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.claim import Claim
from app.models.conflict import Conflict, ConflictClaim
from app.models.enums import (
    AWAITING_REVIEW_STATUSES,
    ClaimStatus,
    ClaimType,
    ConflictStatus,
    HandoverLifecycleStatus,
    KnowledgeGapStatus,
    SuccessorTaskStatus,
)
from app.models.handover import Handover, HandoverVersion
from app.models.phase5 import KnowledgeGap, SuccessorTask
from app.services.handover_service import HandoverService
from app.services.readiness_service import ReadinessService

logger = logging.getLogger("continuum.successor.workspace")

_APPROVED = ClaimStatus.VERIFIED

#: Sections B–I: (key, title, intro, claim categories, no-content message).
_SECTION_SPECS: tuple[tuple[str, str, str, tuple[ClaimType, ...], str], ...] = (
    (
        "project_overview",
        "Project Overview",
        "What this project is and where it currently stands.",
        (ClaimType.ARCHITECTURE, ClaimType.STATUS, ClaimType.PROCESS, ClaimType.OTHER),
        "No approved statement describes the project yet.",
    ),
    (
        "key_decisions",
        "Key Decisions",
        "Decisions that were made, with the reasoning recorded where it exists.",
        (ClaimType.DECISION,),
        "No decision has been approved yet.",
    ),
    (
        "technical_architecture",
        "Technical Architecture",
        "Architecture, dependencies and technical constraints.",
        (ClaimType.ARCHITECTURE, ClaimType.DEPENDENCY, ClaimType.TECHNICAL_CONSTRAINT),
        "No architecture or dependency has been approved yet.",
    ),
    (
        "responsibilities",
        "Responsibilities",
        "Who owns what, based only on approved statements.",
        (ClaimType.OWNERSHIP, ClaimType.RESPONSIBILITY),
        "No ownership or responsibility statement has been approved yet.",
    ),
    (
        "current_work",
        "Current Work",
        "Work that is unfinished or still in progress.",
        (ClaimType.TASK, ClaimType.UNFINISHED_WORK),
        "No outstanding work has been approved yet.",
    ),
    (
        "risks_and_blockers",
        "Risks and Blockers",
        "Risks and anything currently blocking progress.",
        (ClaimType.RISK,),
        "No risk has been approved yet.",
    ),
    (
        "operational_procedures",
        "Operational Procedures",
        "How to operate, deploy and recover the project.",
        (ClaimType.OPERATIONAL_PROCEDURE,),
        "No operational procedure has been approved yet.",
    ),
    (
        "open_questions",
        "Open Questions",
        "Questions that are still unanswered.",
        (ClaimType.OPEN_QUESTION,),
        "No open question has been recorded.",
    ),
)


def build_workspace(db: Session, project_id: uuid.UUID) -> dict[str, Any]:
    """Assemble the successor workspace payload for one project."""
    approved = list(
        db.execute(
            select(Claim).where(Claim.project_id == project_id, Claim.status == _APPROVED)
        ).scalars().all()
    )
    by_type: dict[ClaimType, list[Claim]] = {}
    for claim in approved:
        by_type.setdefault(claim.claim_type, []).append(claim)

    evidence = HandoverService(db).evidence_index([claim.id for claim in approved])
    readiness = ReadinessService(db).latest(project_id)
    tasks = list(
        db.execute(
            select(SuccessorTask)
            .where(SuccessorTask.project_id == project_id)
            .order_by(SuccessorTask.created_at.asc(), SuccessorTask.id.asc())
        ).scalars().all()
    )
    gaps = list(
        db.execute(
            select(KnowledgeGap)
            .where(
                KnowledgeGap.project_id == project_id,
                KnowledgeGap.status == KnowledgeGapStatus.OPEN,
            )
            .order_by(KnowledgeGap.created_at.asc())
        ).scalars().all()
    )
    open_conflicts = list(
        db.execute(
            select(Conflict).where(
                Conflict.project_id == project_id,
                Conflict.status == ConflictStatus.OPEN,
            )
        ).scalars().all()
    )
    pending_review = int(
        len(
            [
                claim
                for claim in db.execute(
                    select(Claim).where(
                        Claim.project_id == project_id,
                        Claim.status.in_(
                            [status.value for status in AWAITING_REVIEW_STATUSES]
                        ),
                    )
                ).scalars().all()
            ]
        )
    )

    published = db.execute(
        select(HandoverVersion)
        .join(Handover, Handover.id == HandoverVersion.handover_id)
        .where(
            Handover.project_id == project_id,
            HandoverVersion.status == HandoverLifecycleStatus.PUBLISHED,
        )
        .order_by(HandoverVersion.version_number.desc())
        .limit(1)
    ).scalar_one_or_none()

    def item(claim: Claim) -> dict[str, Any]:
        return {
            "claim_id": str(claim.id),
            "text": claim.text,
            "claim_type": claim.claim_type.value,
            "entity": claim.entity,
            "critical": claim.critical,
            "revision_number": claim.revision_number,
            "evidence": evidence.get(claim.id, []),
        }

    sections: list[dict[str, Any]] = [
        _start_here(readiness, tasks, gaps, open_conflicts, published, len(approved))
    ]
    for key, title, intro, claim_types, empty_message in _SECTION_SPECS:
        items: list[dict[str, Any]] = []
        for claim_type in claim_types:
            items.extend(item(claim) for claim in by_type.get(claim_type, []))
        sections.append(
            {
                "key": key,
                "title": title,
                "intro": intro,
                "items": items,
                "empty_reason": None if items else empty_message,
            }
        )

    # J. First Actions — the checklist, plus suggested documentation actions.
    sections.append(
        {
            "key": "first_actions",
            "title": "First Actions",
            "intro": (
                "Suggested starting points. Items marked 'suggested' are system "
                "recommendations, not established obligations; no owner or deadline "
                "has been invented."
            ),
            "items": [
                {
                    "task_id": str(task.id),
                    "title": task.title,
                    "description": task.description,
                    "priority": task.priority.value,
                    "status": task.status.value,
                    "owner": task.owner,
                    "completion_criteria": task.completion_criteria,
                    "origin": task.origin,
                    "supporting_claim_ids": list(task.supporting_claim_ids or []),
                    "dependency_ids": list(task.dependency_ids or []),
                }
                for task in tasks
            ],
            "empty_reason": (
                None
                if tasks
                else "No successor tasks have been derived yet. Run the checklist."
            ),
        }
    )

    return {
        "project_id": str(project_id),
        "sections": sections,
        "handover": {
            "published_version_id": str(published.id) if published else None,
            "published_version_number": published.version_number if published else None,
            "published_at": published.created_at.isoformat() if published else None,
        },
        "counts": {
            "approved_claims": len(approved),
            "pending_review": pending_review,
            "open_conflicts": len(open_conflicts),
            "open_gaps": len(gaps),
            "tasks": len(tasks),
            "tasks_open": sum(
                1 for task in tasks if task.status != SuccessorTaskStatus.COMPLETED
            ),
        },
        "open_gaps": [
            {
                "gap_id": str(gap.id),
                "gap_key": gap.gap_key,
                "category": gap.category,
                "description": gap.description,
                "criticality": gap.criticality.value,
                "suggested_resolution": gap.suggested_resolution,
                "status": gap.status.value,
            }
            for gap in gaps
        ],
    }


def _start_here(
    readiness: Any,
    tasks: list[SuccessorTask],
    gaps: list[KnowledgeGap],
    open_conflicts: list[Conflict],
    published: HandoverVersion | None,
    approved_count: int,
) -> dict[str, Any]:
    if readiness is None:
        readiness_line = (
            "No readiness evaluation has been run yet, so the completeness of this "
            "handover has not been assessed."
        )
        score: float | None = None
        band: str | None = None
        blockers: list[Any] = []
    else:
        score = readiness.overall_score
        band = readiness.band.value
        blockers = list(readiness.blockers or [])
        readiness_line = (
            f"Handover readiness is {score:.2f}/100 ({band.replace('_', ' ')}). "
            "This measures how complete the approved knowledge is; it is not proof "
            "that a successor will succeed."
        )

    lines = [
        readiness_line,
        (
            "This workspace only shows knowledge a human reviewer has approved."
            if approved_count
            else "No knowledge has been approved yet, so this workspace is empty."
        ),
        (
            f"{len(open_conflicts)} unresolved conflict(s) and {len(gaps)} open "
            "knowledge gap(s) are recorded below."
        ),
        (
            "A handover has been published."
            if published is not None
            else "No handover has been published yet."
        ),
    ]
    return {
        "key": "start_here",
        "title": "Start Here",
        "intro": "Where to begin and how much you can rely on this handover.",
        "readiness": {
            "score": score,
            "band": band,
            "blocker_count": len(blockers),
            "open_conflict_count": len(open_conflicts),
            "open_gap_count": len(gaps),
            "task_count": len(tasks),
        },
        "blockers": [
            {"code": item.get("code"), "message": item.get("message")} for item in blockers
        ],
        "narrative": lines,
        "items": [],
        "empty_reason": None,
    }


__all__ = ["build_workspace"]
