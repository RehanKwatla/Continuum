"""Project + connected-repository data access."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.models.enums import ProjectStatus
from app.models.project import Project
from app.models.project_repository import ProjectRepository as RepositoryLink
from app.models.source import Source
from app.repositories.base import BaseRepository


class ProjectsRepository(BaseRepository[Project]):
    model = Project

    def create(
        self,
        *,
        workspace_id: uuid.UUID,
        name: str,
        description: str | None = None,
        departing_role: str | None = None,
        successor_role: str | None = None,
        status: ProjectStatus = ProjectStatus.ACTIVE,
    ) -> Project:
        project = Project(
            workspace_id=workspace_id,
            name=name.strip(),
            description=description,
            departing_role=departing_role,
            successor_role=successor_role,
            status=status,
        )
        self.db.add(project)
        return project

    def list_for_workspace(
        self,
        workspace_ids: Sequence[uuid.UUID],
        *,
        search: str | None = None,
        status: ProjectStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Project], int]:
        base = select(Project).where(Project.workspace_id.in_(list(workspace_ids)))
        if search:
            pattern = f"%{search.strip().lower()}%"
            base = base.where(func.lower(Project.name).like(pattern))
        if status is not None:
            base = base.where(Project.status == status)

        total = int(
            self.db.execute(
                select(func.count()).select_from(base.subquery())
            ).scalar_one()
        )
        rows = self.db.execute(
            base.order_by(Project.updated_at.desc()).limit(limit).offset(offset)
        ).scalars().all()
        return list(rows), total

    def all_ids_for_workspaces(self, workspace_ids: Sequence[uuid.UUID]) -> list[uuid.UUID]:
        if not workspace_ids:
            return []
        rows = self.db.execute(
            select(Project.id).where(Project.workspace_id.in_(list(workspace_ids)))
        ).scalars().all()
        return list(rows)

    def list_recent(self, workspace_ids: Sequence[uuid.UUID], limit: int = 5) -> list[Project]:
        if not workspace_ids:
            return []
        rows = self.db.execute(
            select(Project)
            .where(Project.workspace_id.in_(list(workspace_ids)))
            .order_by(Project.updated_at.desc())
            .limit(limit)
        ).scalars().all()
        return list(rows)

    def get_with_repositories(self, project_id: uuid.UUID) -> Project | None:
        return self.db.execute(
            select(Project)
            .where(Project.id == project_id)
            .options(selectinload(Project.repositories))
        ).scalar_one_or_none()

    # --- connected repositories -----------------------------------------
    def list_repositories(self, project_id: uuid.UUID) -> list[RepositoryLink]:
        rows = self.db.execute(
            select(RepositoryLink)
            .where(RepositoryLink.project_id == project_id)
            .order_by(RepositoryLink.connected_at.desc())
        ).scalars().all()
        return list(rows)

    def get_repository(self, project_id: uuid.UUID, full_name: str) -> RepositoryLink | None:
        return self.db.execute(
            select(RepositoryLink).where(
                RepositoryLink.project_id == project_id,
                RepositoryLink.full_name == full_name,
            )
        ).scalar_one_or_none()

    def upsert_repository(
        self,
        *,
        project_id: uuid.UUID,
        full_name: str,
        provider: str = "github",
        external_id: str | None = None,
        description: str | None = None,
        default_branch: str | None = None,
        is_private: bool = False,
        html_url: str | None = None,
        meta: dict | None = None,
    ) -> RepositoryLink:
        existing = self.get_repository(project_id, full_name)
        if existing is not None:
            existing.external_id = external_id or existing.external_id
            existing.description = description or existing.description
            existing.default_branch = default_branch or existing.default_branch
            existing.html_url = html_url or existing.html_url
            existing.is_private = is_private
            existing.meta = meta or existing.meta
            return existing

        link = RepositoryLink(
            project_id=project_id,
            provider=provider,
            full_name=full_name,
            external_id=external_id,
            description=description,
            default_branch=default_branch,
            is_private=is_private,
            html_url=html_url,
            meta=meta or {},
        )
        self.db.add(link)
        return link

    # --- counters --------------------------------------------------------
    def source_count(self, project_id: uuid.UUID) -> int:
        return int(
            self.db.execute(
                select(func.count()).select_from(Source).where(Source.project_id == project_id)
            ).scalar_one()
        )

    def repository_count(self, project_id: uuid.UUID) -> int:
        return int(
            self.db.execute(
                select(func.count())
                .select_from(RepositoryLink)
                .where(RepositoryLink.project_id == project_id)
            ).scalar_one()
        )

    def source_counts_by_project(self, project_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, int]:
        if not project_ids:
            return {}
        rows = self.db.execute(
            select(Source.project_id, func.count())
            .where(Source.project_id.in_(list(project_ids)))
            .group_by(Source.project_id)
        ).all()
        return {row[0]: int(row[1]) for row in rows}

    def repository_counts_by_project(
        self, project_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, int]:
        if not project_ids:
            return {}
        rows = self.db.execute(
            select(RepositoryLink.project_id, func.count())
            .where(RepositoryLink.project_id.in_(list(project_ids)))
            .group_by(RepositoryLink.project_id)
        ).all()
        return {row[0]: int(row[1]) for row in rows}
