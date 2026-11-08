"""Source data access."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select

from app.models.enums import ProcessingStatus, SourceType
from app.models.source import Source
from app.repositories.base import BaseRepository


class SourcesRepository(BaseRepository[Source]):
    model = Source

    def find_by_hash(self, project_id: uuid.UUID, content_hash: str) -> Source | None:
        return self.db.execute(
            select(Source).where(
                Source.project_id == project_id,
                Source.content_hash == content_hash,
            )
        ).scalar_one_or_none()

    def list_for_project(
        self,
        project_id: uuid.UUID,
        *,
        source_type: SourceType | None = None,
        processing_status: ProcessingStatus | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Source], int]:
        base = select(Source).where(Source.project_id == project_id)
        if source_type is not None:
            base = base.where(Source.source_type == source_type)
        if processing_status is not None:
            base = base.where(Source.processing_status == processing_status)
        if search:
            pattern = f"%{search.strip().lower()}%"
            base = base.where(func.lower(Source.source_name).like(pattern))

        total = int(
            self.db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
        )
        rows = self.db.execute(
            base.order_by(Source.created_at.desc()).limit(limit).offset(offset)
        ).scalars().all()
        return list(rows), total

    def counts_by_type(self, project_id: uuid.UUID) -> dict[str, int]:
        rows = self.db.execute(
            select(Source.source_type, func.count())
            .where(Source.project_id == project_id)
            .group_by(Source.source_type)
        ).all()
        return {_value(row[0]): int(row[1]) for row in rows}

    def counts_by_status(self, project_id: uuid.UUID) -> dict[str, int]:
        rows = self.db.execute(
            select(Source.processing_status, func.count())
            .where(Source.project_id == project_id)
            .group_by(Source.processing_status)
        ).all()
        return {_value(row[0]): int(row[1]) for row in rows}

    def counts_for_projects(
        self, project_ids: Sequence[uuid.UUID]
    ) -> tuple[dict[str, int], dict[str, int], int]:
        """Return (type_counts, status_counts, total) across many projects."""
        if not project_ids:
            return {}, {}, 0
        ids = list(project_ids)
        type_rows = self.db.execute(
            select(Source.source_type, func.count())
            .where(Source.project_id.in_(ids))
            .group_by(Source.source_type)
        ).all()
        status_rows = self.db.execute(
            select(Source.processing_status, func.count())
            .where(Source.project_id.in_(ids))
            .group_by(Source.processing_status)
        ).all()
        type_counts = {_value(row[0]): int(row[1]) for row in type_rows}
        status_counts = {_value(row[0]): int(row[1]) for row in status_rows}
        return type_counts, status_counts, sum(type_counts.values())

    def recent_for_workspace(
        self, workspace_ids: Sequence[uuid.UUID], limit: int = 8
    ) -> list[tuple[Source, uuid.UUID, str]]:
        from app.models.project import Project

        if not workspace_ids:
            return []
        rows = self.db.execute(
            select(Source, Project.id, Project.name)
            .join(Project, Project.id == Source.project_id)
            .where(Project.workspace_id.in_(list(workspace_ids)))
            .order_by(Source.created_at.desc())
            .limit(limit)
        ).all()
        return [(row[0], row[1], row[2]) for row in rows]


def _value(raw: object) -> str:
    return getattr(raw, "value", str(raw))
