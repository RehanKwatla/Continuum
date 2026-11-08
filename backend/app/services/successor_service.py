"""Successor task checklist (Phase 5 §5).

Tasks are **derived from approved knowledge**; nothing here invents an owner, a
deadline or an obligation:

* a task is created from an approved ``task`` / ``unfinished_work`` claim;
* an approved ``open_question`` becomes a *suggested* action ("answer this
  question"), clearly labelled ``suggested`` rather than presented as an
  established obligation;
* a missing *critical* readiness requirement becomes a suggested action too, so
  the successor is told what documentation is absent;
* an owner is only ever copied from an approved ``ownership`` statement that
  covers the same entity — if no such statement exists the owner stays empty;
* no deadline is ever set (the model has no deadline field at all).

Re-deriving the checklist is idempotent: the ``(project_id, origin_claim_id)``
unique constraint means running it twice cannot duplicate a task, and
suggested actions are de-duplicated on their stable title.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationAppError
from app.models.claim import Claim
from app.models.conflict import Conflict, ConflictClaim
from app.models.enums import (
    ClaimStatus,
    ClaimType,
    ConflictStatus,
    RequirementCriticality,
    SuccessorTaskPriority,
    SuccessorTaskStatus,
)
from app.models.phase5 import SuccessorTask
from app.services import audit_service

logger = logging.getLogger("continuum.successor")

_APPROVED = ClaimStatus.VERIFIED

#: Claim categories that become actionable successor tasks.
_TASK_CLAIM_TYPES: tuple[ClaimType, ...] = (
    ClaimType.TASK,
    ClaimType.UNFINISHED_WORK,
)

#: Keywords that mark a statement as describing a blocked / dependent item.
_BLOCKER_KEYWORDS: tuple[str, ...] = (
    "blocked",
    "blocker",
    "waiting on",
    "depends on",
    "dependent on",
    "once ",
    "after ",
)

_COMPLETION_CRITERIA: dict[str, str] = {
    "task": (
        "The described work is finished, and the change is recorded against the "
        "supporting evidence for this task."
    ),
    "unfinished_work": (
        "The outstanding work described by the supporting statement is finished and "
        "the supporting claim can be superseded or updated."
    ),
    "open_question": (
        "The question is answered and the answer is recorded as an approved project "
        "claim."
    ),
    "gap": (
        "The missing knowledge is documented and approved, or the gap is explicitly "
        "accepted as a risk."
    ),
}


def _priority_for_claim(claim: Claim) -> SuccessorTaskPriority:
    if claim.critical:
        return SuccessorTaskPriority.HIGH
    if claim.claim_type in {ClaimType.UNFINISHED_WORK, ClaimType.RISK}:
        return SuccessorTaskPriority.HIGH
    return SuccessorTaskPriority.MEDIUM


def _priority_for_criticality(criticality: str) -> SuccessorTaskPriority:
    mapping = {
        RequirementCriticality.CRITICAL.value: SuccessorTaskPriority.HIGH,
        RequirementCriticality.IMPORTANT.value: SuccessorTaskPriority.MEDIUM,
        RequirementCriticality.OPTIONAL.value: SuccessorTaskPriority.LOW,
    }
    return mapping.get(criticality, SuccessorTaskPriority.MEDIUM)


def _is_blocker_text(text: str) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in _BLOCKER_KEYWORDS)


class SuccessorService:
    """Derives, lists and updates a project's successor task checklist."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------
    def list_tasks(
        self, project_id: uuid.UUID, *, status: SuccessorTaskStatus | None = None
    ) -> list[SuccessorTask]:
        query = select(SuccessorTask).where(SuccessorTask.project_id == project_id)
        if status is not None:
            query = query.where(SuccessorTask.status == status)
        return list(
            self.db.execute(
                query.order_by(SuccessorTask.created_at.asc(), SuccessorTask.id.asc())
            ).scalars().all()
        )

    def get(self, project_id: uuid.UUID, task_id: uuid.UUID) -> SuccessorTask:
        task = self.db.get(SuccessorTask, task_id)
        if task is None or task.project_id != project_id:
            raise NotFoundError("Successor task not found.")
        return task

    def approved_claims(self, project_id: uuid.UUID) -> list[Claim]:
        return list(
            self.db.execute(
                select(Claim).where(
                    Claim.project_id == project_id, Claim.status == _APPROVED
                )
            ).scalars().all()
        )

    # ------------------------------------------------------------------
    # Derivation
    # ------------------------------------------------------------------
    def derive(
        self,
        project_id: uuid.UUID,
        *,
        user_id: uuid.UUID | None = None,
        workspace_id: uuid.UUID | None = None,
        gaps: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Derive the checklist from approved claims (+ optional gaps).

        Idempotent: existing tasks (matched on origin claim / stable title) are
        left untouched, so repeated runs never duplicate work.
        """
        approved = self.approved_claims(project_id)
        existing = self.list_tasks(project_id)
        existing_claim_origins = {
            task.origin_claim_id for task in existing if task.origin_claim_id is not None
        }
        existing_titles = {task.title for task in existing}

        ownership_by_entity = self._ownership_index(approved)
        conflicted = self._conflicted_claim_ids(project_id)

        created: list[SuccessorTask] = []

        # 1. Established obligations: approved task / unfinished_work claims.
        for claim in approved:
            if claim.claim_type not in _TASK_CLAIM_TYPES:
                continue
            if claim.id in existing_claim_origins:
                continue
            task = self._build_task(
                project_id,
                claim=claim,
                user_id=user_id,
                ownership_by_entity=ownership_by_entity,
                origin="derived",
            )
            if claim.id in conflicted:
                task.status = SuccessorTaskStatus.BLOCKED
            created.append(task)
            existing_titles.add(task.title)

        # 2. Suggested next actions: approved open questions.
        for claim in approved:
            if claim.claim_type != ClaimType.OPEN_QUESTION:
                continue
            if claim.id in existing_claim_origins:
                continue
            task = self._build_task(
                project_id,
                claim=claim,
                user_id=user_id,
                ownership_by_entity=ownership_by_entity,
                origin="suggested",
            )
            created.append(task)
            existing_titles.add(task.title)

        # 3. Suggested next actions: missing critical readiness requirements.
        for gap in gaps or []:
            criticality = str(gap.get("criticality") or RequirementCriticality.IMPORTANT.value)
            if criticality != RequirementCriticality.CRITICAL.value:
                continue
            title = f"Document missing knowledge: {gap.get('gap_key') or gap.get('category')}"
            if title in existing_titles:
                continue
            created.append(
                SuccessorTask(
                    project_id=project_id,
                    title=title[:300],
                    description=str(gap.get("description") or gap.get("missing_information") or ""),
                    priority=_priority_for_criticality(criticality),
                    status=SuccessorTaskStatus.NOT_STARTED,
                    owner=None,
                    completion_criteria=_COMPLETION_CRITERIA["gap"],
                    supporting_claim_ids=[],
                    dependency_ids=[],
                    origin="suggested",
                    origin_claim_id=None,
                    created_by_id=user_id,
                    updated_by_id=user_id,
                )
            )
            existing_titles.add(title)

        for task in created:
            self.db.add(task)
        self.db.flush()

        # Link dependencies between the newly created and existing tasks.
        self._link_dependencies(project_id, created)

        if created:
            audit_service.record(
                self.db,
                action="successor_tasks_derived",
                user_id=user_id,
                workspace_id=workspace_id,
                resource_type="project",
                resource_id=project_id,
                metadata={
                    "project_id": str(project_id),
                    "created": len(created),
                    "derived": sum(1 for t in created if t.origin == "derived"),
                    "suggested": sum(1 for t in created if t.origin == "suggested"),
                },
            )

        return {
            "created": len(created),
            "total": len(self.list_tasks(project_id)),
            "task_ids": [str(task.id) for task in created],
        }

    def _build_task(
        self,
        project_id: uuid.UUID,
        *,
        claim: Claim,
        user_id: uuid.UUID | None,
        ownership_by_entity: dict[str, Claim],
        origin: str,
    ) -> SuccessorTask:
        entity_key = (claim.entity or "").strip().lower()
        owner_claim = ownership_by_entity.get(entity_key) if entity_key else None
        owner: str | None = None
        supporting = [str(claim.id)]
        if owner_claim is not None:
            owner = f"{owner_claim.text}"[:255]
            supporting.append(str(owner_claim.id))
        criteria_key = "task"
        if claim.claim_type == ClaimType.UNFINISHED_WORK:
            criteria_key = "unfinished_work"
        elif claim.claim_type == ClaimType.OPEN_QUESTION:
            criteria_key = "open_question"
        prefix = "Answer: " if origin == "suggested" else ""
        return SuccessorTask(
            project_id=project_id,
            title=f"{prefix}{claim.text}"[:300],
            description=claim.reasoning_summary or None,
            priority=_priority_for_claim(claim),
            status=SuccessorTaskStatus.NOT_STARTED,
            owner=owner,
            completion_criteria=_COMPLETION_CRITERIA[criteria_key],
            supporting_claim_ids=supporting,
            dependency_ids=[],
            origin=origin,
            origin_claim_id=claim.id,
            created_by_id=user_id,
            updated_by_id=user_id,
        )

    def _ownership_index(self, approved: list[Claim]) -> dict[str, Claim]:
        """``{entity: ownership claim}`` — only from approved ownership claims."""
        index: dict[str, Claim] = {}
        for claim in approved:
            if claim.claim_type != ClaimType.OWNERSHIP:
                continue
            key = (claim.entity or "").strip().lower()
            if key and key not in index:
                index[key] = claim
        return index

    def _conflicted_claim_ids(self, project_id: uuid.UUID) -> set[uuid.UUID]:
        rows = self.db.execute(
            select(ConflictClaim.claim_id)
            .join(Conflict, Conflict.id == ConflictClaim.conflict_id)
            .where(Conflict.project_id == project_id, Conflict.status == ConflictStatus.OPEN)
        ).all()
        return {claim_id for (claim_id,) in rows}

    def _link_dependencies(
        self, project_id: uuid.UUID, created: list[SuccessorTask]
    ) -> None:
        """Link tasks that share an entity when one statement describes a blocker.

        A task that depends on an incomplete prerequisite is marked ``Blocked``.
        The rule is deterministic: same entity, and the dependent statement
        contains an explicit dependency/blocker phrase.
        """
        if not created:
            return
        all_tasks = self.list_tasks(project_id)
        by_entity: dict[str, list[SuccessorTask]] = {}
        for task in all_tasks:
            key = self._entity_of_task(task)
            if key:
                by_entity.setdefault(key, []).append(task)

        for task in created:
            key = self._entity_of_task(task)
            if not key:
                continue
            origin_text = self._origin_text(task)
            if not _is_blocker_text(origin_text):
                continue
            dependencies = [
                other.id
                for other in by_entity.get(key, [])
                if other.id != task.id and other.status != SuccessorTaskStatus.COMPLETED
            ]
            if not dependencies:
                continue
            task.dependency_ids = sorted(str(item) for item in dependencies)
            if task.status == SuccessorTaskStatus.NOT_STARTED:
                task.status = SuccessorTaskStatus.BLOCKED
        self.db.flush()

    def _entity_of_task(self, task: SuccessorTask) -> str:
        if task.origin_claim_id is None:
            return ""
        claim = self.db.get(Claim, task.origin_claim_id)
        if claim is None:
            return ""
        return (claim.entity or "").strip().lower()

    def _origin_text(self, task: SuccessorTask) -> str:
        if task.origin_claim_id is None:
            return task.title
        claim = self.db.get(Claim, task.origin_claim_id)
        return claim.text if claim is not None else task.title

    # ------------------------------------------------------------------
    # Updates (§5 — successors may update progress)
    # ------------------------------------------------------------------
    def update_status(
        self,
        project_id: uuid.UUID,
        task_id: uuid.UUID,
        *,
        status: SuccessorTaskStatus,
        user_id: uuid.UUID | None = None,
        workspace_id: uuid.UUID | None = None,
        note: str | None = None,
    ) -> SuccessorTask:
        task = self.get(project_id, task_id)
        previous = task.status
        if previous == status and not note:
            return task
        task.status = status
        task.updated_by_id = user_id
        unblocked: list[str] = []
        if status == SuccessorTaskStatus.COMPLETED:
            unblocked = self._recompute_dependents(project_id, completed_id=task.id)
        audit_service.record(
            self.db,
            action="successor_task_status_changed",
            user_id=user_id,
            workspace_id=workspace_id,
            resource_type="successor_task",
            resource_id=task.id,
            metadata={
                "project_id": str(project_id),
                "from": previous.value,
                "to": status.value,
                "note": note or "",
                "unblocked": unblocked,
            },
        )
        self.db.flush()
        return task

    def _recompute_dependents(
        self, project_id: uuid.UUID, *, completed_id: uuid.UUID
    ) -> list[str]:
        """Unblock tasks whose prerequisites are all now complete."""
        unblocked: list[str] = []
        for task in self.list_tasks(project_id):
            if not task.dependency_ids:
                continue
            if str(completed_id) not in task.dependency_ids:
                continue
            if task.status != SuccessorTaskStatus.BLOCKED:
                continue
            remaining = [
                dep for dep in task.dependency_ids if dep != str(completed_id)
            ]
            still_blocked = False
            for dep in remaining:
                try:
                    dep_task = self.db.get(SuccessorTask, uuid.UUID(dep))
                except (ValueError, TypeError):
                    continue
                if dep_task is not None and dep_task.status != SuccessorTaskStatus.COMPLETED:
                    still_blocked = True
                    break
            if not still_blocked:
                task.status = SuccessorTaskStatus.NOT_STARTED
                unblocked.append(str(task.id))
        return unblocked

    def add_manual_task(
        self,
        project_id: uuid.UUID,
        *,
        title: str,
        description: str | None = None,
        priority: SuccessorTaskPriority = SuccessorTaskPriority.MEDIUM,
        completion_criteria: str | None = None,
        user_id: uuid.UUID | None = None,
        workspace_id: uuid.UUID | None = None,
    ) -> SuccessorTask:
        """A successor-authored task. Owner is never inferred for these."""
        if not title or not title.strip():
            raise ValidationAppError("A task title is required.", code="task_title_required")
        task = SuccessorTask(
            project_id=project_id,
            title=title.strip()[:300],
            description=description,
            priority=priority,
            status=SuccessorTaskStatus.NOT_STARTED,
            owner=None,
            completion_criteria=completion_criteria,
            supporting_claim_ids=[],
            dependency_ids=[],
            origin="manual",
            origin_claim_id=None,
            created_by_id=user_id,
            updated_by_id=user_id,
        )
        self.db.add(task)
        self.db.flush()
        audit_service.record(
            self.db,
            action="successor_task_created",
            user_id=user_id,
            workspace_id=workspace_id,
            resource_type="successor_task",
            resource_id=task.id,
            metadata={"project_id": str(project_id), "title": task.title},
        )
        return task


__all__ = ["SuccessorService"]
