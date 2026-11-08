"""Knowledge dependency analysis and missing-knowledge detection (§6–§7).

Knowledge dependency (§6)
-------------------------
The module looks for project knowledge whose *documented* basis rests on a
single person. It does **not** infer expertise from a name appearing often:
a person only counts when they authored a source that actually supports an
approved claim (or when an approved ownership/responsibility statement names
them). Where that evidence is absent the record is reported as ``Unknown``
rather than guessed, and a reviewer can override the computed risk with an
audited note.

Missing knowledge (§7)
----------------------
The engine compares the readiness requirements against the approved knowledge
and records every unmet requirement as a gap. Gaps are never auto-filled and a
gap's workflow status (Open / In Progress / Resolved / Accepted Risk) is
preserved across re-runs.
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationAppError
from app.models.claim import Claim
from app.models.enums import (
    AccessLabel,
    ClaimStatus,
    ClaimType,
    DependencyRiskStatus,
    KnowledgeGapStatus,
    RequirementCompletion,
    RequirementCriticality,
)
from app.models.evidence import Evidence
from app.models.phase5 import KnowledgeDependency, KnowledgeGap
from app.models.source import Source
from app.services import audit_service

logger = logging.getLogger("continuum.knowledge")

_APPROVED = ClaimStatus.VERIFIED

#: Claim categories whose single-person concentration is treated as critical.
_CRITICAL_KNOWLEDGE_TYPES: tuple[ClaimType, ...] = (
    ClaimType.OWNERSHIP,
    ClaimType.RESPONSIBILITY,
    ClaimType.OPERATIONAL_PROCEDURE,
    ClaimType.DEPENDENCY,
    ClaimType.DECISION,
)

#: Concentration at or above this fraction is "Moderate" when several people
#: are involved.
_MODERATE_CONCENTRATION = 0.75


def _now() -> datetime:
    return datetime.now(timezone.utc)


class KnowledgeRiskService:
    """Computes single-person knowledge risk and missing-knowledge gaps."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # §6 — knowledge dependency analysis
    # ------------------------------------------------------------------
    def list_dependencies(self, project_id: uuid.UUID) -> list[KnowledgeDependency]:
        return list(
            self.db.execute(
                select(KnowledgeDependency)
                .where(KnowledgeDependency.project_id == project_id)
                .order_by(
                    KnowledgeDependency.dependency_level.desc(),
                    KnowledgeDependency.dependency_key.asc(),
                )
            ).scalars().all()
        )

    def get_dependency(
        self, project_id: uuid.UUID, dependency_id: uuid.UUID
    ) -> KnowledgeDependency:
        record = self.db.get(KnowledgeDependency, dependency_id)
        if record is None or record.project_id != project_id:
            raise NotFoundError("Knowledge dependency not found.")
        return record

    def analyse_dependencies(
        self,
        project_id: uuid.UUID,
        *,
        user_id: uuid.UUID | None = None,
        workspace_id: uuid.UUID | None = None,
    ) -> list[KnowledgeDependency]:
        """Recompute single-person knowledge concentration for every entity."""
        approved = list(
            self.db.execute(
                select(Claim).where(
                    Claim.project_id == project_id, Claim.status == _APPROVED
                )
            ).scalars().all()
        )
        ownership_entities = {
            (c.entity or "").strip().lower()
            for c in approved
            if c.claim_type == ClaimType.OWNERSHIP and (c.entity or "").strip()
        }

        # claim -> supporting sources (author + id + restricted flag)
        claim_ids = [c.id for c in approved]
        authors_by_claim: dict[uuid.UUID, list[str]] = defaultdict(list)
        sources_by_claim: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
        if claim_ids:
            rows = self.db.execute(
                select(Evidence.claim_id, Source.author, Source.id, Source.access_label)
                .join(Source, Source.id == Evidence.source_id)
                .where(Evidence.claim_id.in_(claim_ids))
            ).all()
            for claim_id, author, source_id, access_label in rows:
                name = (author or "").strip()
                if name:
                    authors_by_claim[claim_id].append(name)
                if str(access_label.value) != AccessLabel.RESTRICTED.value:
                    sources_by_claim[claim_id].append(source_id)

        by_entity: dict[str, list[Claim]] = defaultdict(list)
        for claim in approved:
            key = (claim.entity or "").strip()
            if key:
                by_entity[key].append(claim)

        existing = {
            record.dependency_key: record for record in self.list_dependencies(project_id)
        }
        computed: list[KnowledgeDependency] = []

        for entity, claims in by_entity.items():
            person_claims: dict[str, int] = defaultdict(int)
            involved: list[str] = []
            related_sources: list[uuid.UUID] = []
            for claim in claims:
                names = authors_by_claim.get(claim.id, [])
                for name in dict.fromkeys(names):
                    person_claims[name] += 1
                    if name not in involved:
                        involved.append(name)
                for source_id in sources_by_claim.get(claim.id, []):
                    if source_id not in related_sources:
                        related_sources.append(source_id)

            considered = sum(person_claims.values())
            is_critical_knowledge = any(
                c.critical or c.claim_type in _CRITICAL_KNOWLEDGE_TYPES for c in claims
            )

            if considered == 0:
                risk = DependencyRiskStatus.UNKNOWN
                level = 0.0
                summary = (
                    f"No sourced authorship data is available for '{entity}', so no "
                    "single-person dependency can be established."
                )
                missing = (
                    "Evidence with an identified author is required before a knowledge "
                    "dependency can be assessed."
                )
            else:
                leading = max(person_claims.items(), key=lambda item: (item[1], item[0]))
                level = round(leading[1] / considered, 4)
                if len(involved) == 1:
                    risk = (
                        DependencyRiskStatus.HIGH
                        if is_critical_knowledge
                        else DependencyRiskStatus.MODERATE
                    )
                    summary = (
                        f"All {considered} sourced claim(s) about '{entity}' trace back to "
                        f"a single author ({leading[0]})."
                    )
                elif level >= _MODERATE_CONCENTRATION:
                    risk = DependencyRiskStatus.MODERATE
                    summary = (
                        f"{leading[1]} of {considered} sourced claim(s) about '{entity}' "
                        f"trace back to {leading[0]}."
                    )
                else:
                    risk = DependencyRiskStatus.LOW
                    summary = (
                        f"Knowledge about '{entity}' is spread across {len(involved)} "
                        "authors."
                    )
                missing = self._missing_backup(entity, ownership_entities, len(involved))

            key = entity.lower()
            record = existing.get(key)
            if record is None:
                record = KnowledgeDependency(
                    project_id=project_id,
                    dependency_key=key[:300],
                    entity=entity[:300],
                    claim_ids=sorted(str(c.id) for c in claims),
                    related_source_ids=sorted(str(item) for item in related_sources),
                    involved_people=sorted(involved),
                    dependency_level=level,
                    risk_status=risk,
                    evidence_summary=summary,
                    missing_backup_information=missing,
                    override={},
                    computed_at=_now(),
                )
                self.db.add(record)
                existing[key] = record
            else:
                record.entity = entity[:300]
                record.claim_ids = sorted(str(c.id) for c in claims)
                record.related_source_ids = sorted(str(item) for item in related_sources)
                record.involved_people = sorted(involved)
                record.dependency_level = level
                record.risk_status = risk
                record.evidence_summary = summary
                record.missing_backup_information = missing
                record.computed_at = _now()
            computed.append(record)

        self.db.flush()
        audit_service.record(
            self.db,
            action="knowledge_dependencies_analysed",
            user_id=user_id,
            workspace_id=workspace_id,
            resource_type="project",
            resource_id=project_id,
            metadata={
                "project_id": str(project_id),
                "entities": len(computed),
                "high_risk": sum(
                    1 for item in computed if item.risk_status == DependencyRiskStatus.HIGH
                ),
            },
        )
        return computed

    def _missing_backup(
        self, entity: str, ownership_entities: set[str], author_count: int
    ) -> str | None:
        has_owner = entity.strip().lower() in ownership_entities
        if author_count == 1 and not has_owner:
            return (
                f"Only one person's sourced knowledge covers '{entity}' and no approved "
                "ownership statement names an owner or backup."
            )
        if author_count == 1:
            return (
                f"Only one person's sourced knowledge covers '{entity}'; no backup "
                "contributor is documented."
            )
        if not has_owner:
            return f"No approved ownership statement covers '{entity}'."
        return None

    def override_dependency(
        self,
        project_id: uuid.UUID,
        dependency_id: uuid.UUID,
        *,
        risk_status: DependencyRiskStatus | None,
        note: str,
        user_id: uuid.UUID | None,
        workspace_id: uuid.UUID | None,
    ) -> KnowledgeDependency:
        """Apply (or clear) a reviewer override, with an audit trail."""
        if not note or not note.strip():
            raise ValidationAppError(
                "A note is required when overriding a knowledge dependency.",
                code="override_note_required",
            )
        record = self.get_dependency(project_id, dependency_id)
        if risk_status is None:
            record.override = {}
        else:
            record.override = {
                "risk_status": risk_status.value,
                "note": note.strip()[:2000],
                "by_id": str(user_id) if user_id else None,
                "at": _now().isoformat(),
            }
        audit_service.record(
            self.db,
            action="knowledge_dependency_overridden",
            user_id=user_id,
            workspace_id=workspace_id,
            resource_type="knowledge_dependency",
            resource_id=record.id,
            metadata={
                "project_id": str(project_id),
                "computed": record.risk_status.value,
                "override": risk_status.value if risk_status else None,
                "note": note.strip()[:2000],
            },
        )
        self.db.flush()
        return record

    # ------------------------------------------------------------------
    # §7 — missing knowledge detection
    # ------------------------------------------------------------------
    def list_gaps(
        self, project_id: uuid.UUID, *, status: KnowledgeGapStatus | None = None
    ) -> list[KnowledgeGap]:
        query = select(KnowledgeGap).where(KnowledgeGap.project_id == project_id)
        if status is not None:
            query = query.where(KnowledgeGap.status == status)
        return list(
            self.db.execute(
                query.order_by(KnowledgeGap.created_at.asc(), KnowledgeGap.id.asc())
            ).scalars().all()
        )

    def get_gap(self, project_id: uuid.UUID, gap_id: uuid.UUID) -> KnowledgeGap:
        gap = self.db.get(KnowledgeGap, gap_id)
        if gap is None or gap.project_id != project_id:
            raise NotFoundError("Knowledge gap not found.")
        return gap

    def detect_gaps(
        self,
        project_id: uuid.UUID,
        *,
        requirements: Iterable[Any],
        dependencies: Iterable[KnowledgeDependency] = (),
        user_id: uuid.UUID | None = None,
        workspace_id: uuid.UUID | None = None,
    ) -> list[KnowledgeGap]:
        """Upsert a gap for every unmet requirement (and high-risk dependency).

        ``requirements`` may be :class:`RequirementResult` objects or the
        ``dict`` form stored on an evaluation. A gap's existing workflow status
        is never reset by a re-run.
        """
        existing = {gap.gap_key: gap for gap in self.list_gaps(project_id)}
        produced: list[KnowledgeGap] = []
        opened = 0

        for raw in requirements:
            item = raw.to_dict() if hasattr(raw, "to_dict") else dict(raw)
            completion = str(item.get("completion", ""))
            if completion in {
                RequirementCompletion.COMPLETE.value,
                "",
            }:
                continue
            requirement_id = str(item.get("requirement_id"))
            description = (
                f"{item.get('description', '')} — {item.get('evaluation_reason', '')}"
            ).strip(" —")
            criticality = str(item.get("criticality") or RequirementCriticality.IMPORTANT.value)
            gap = existing.get(requirement_id)
            if gap is None:
                gap = KnowledgeGap(
                    project_id=project_id,
                    gap_key=requirement_id[:160],
                    category=str(item.get("gap_category") or "other")[:64],
                    description=description,
                    criticality=RequirementCriticality(criticality),
                    related_claim_ids=list(item.get("supporting_claim_ids") or []),
                    related_source_ids=list(item.get("supporting_source_ids") or []),
                    suggested_resolution=item.get("suggested_resolution") or None,
                    status=KnowledgeGapStatus.OPEN,
                )
                self.db.add(gap)
                existing[requirement_id] = gap
                opened += 1
            else:
                gap.category = str(item.get("gap_category") or "other")[:64]
                gap.description = description
                gap.criticality = RequirementCriticality(criticality)
                gap.related_claim_ids = list(item.get("supporting_claim_ids") or [])
                gap.related_source_ids = list(item.get("supporting_source_ids") or [])
                gap.suggested_resolution = item.get("suggested_resolution") or None
            produced.append(gap)

        for dependency in dependencies:
            if dependency.risk_status != DependencyRiskStatus.HIGH:
                continue
            key = f"dependency:{dependency.dependency_key}"[:160]
            gap = existing.get(key)
            description = (
                f"Critical knowledge about '{dependency.entity}' depends on a single "
                f"person. {dependency.evidence_summary or ''}"
            ).strip()
            if gap is None:
                gap = KnowledgeGap(
                    project_id=project_id,
                    gap_key=key,
                    category="knowledge_dependency",
                    description=description,
                    criticality=RequirementCriticality.IMPORTANT,
                    related_claim_ids=list(dependency.claim_ids or []),
                    related_source_ids=list(dependency.related_source_ids or []),
                    suggested_resolution=(
                        dependency.missing_backup_information
                        or "Document a backup owner for this knowledge."
                    ),
                    status=KnowledgeGapStatus.OPEN,
                )
                self.db.add(gap)
                existing[key] = gap
                opened += 1
            else:
                gap.description = description
                gap.related_claim_ids = list(dependency.claim_ids or [])
                gap.related_source_ids = list(dependency.related_source_ids or [])
            produced.append(gap)

        self.db.flush()
        audit_service.record(
            self.db,
            action="knowledge_gaps_detected",
            user_id=user_id,
            workspace_id=workspace_id,
            resource_type="project",
            resource_id=project_id,
            metadata={
                "project_id": str(project_id),
                "gaps": len(produced),
                "opened": opened,
            },
        )
        return produced

    def update_gap_status(
        self,
        project_id: uuid.UUID,
        gap_id: uuid.UUID,
        *,
        status: KnowledgeGapStatus,
        user_id: uuid.UUID | None = None,
        workspace_id: uuid.UUID | None = None,
        note: str | None = None,
    ) -> KnowledgeGap:
        gap = self.get_gap(project_id, gap_id)
        previous = gap.status
        gap.status = status
        gap.reviewed_by_id = user_id
        audit_service.record(
            self.db,
            action="knowledge_gap_status_changed",
            user_id=user_id,
            workspace_id=workspace_id,
            resource_type="knowledge_gap",
            resource_id=gap.id,
            metadata={
                "project_id": str(project_id),
                "gap_key": gap.gap_key,
                "from": previous.value,
                "to": status.value,
                "note": note or "",
            },
        )
        self.db.flush()
        return gap


__all__ = ["KnowledgeRiskService"]
