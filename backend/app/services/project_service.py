"""Project service: CRUD, aggregation and dashboard statistics."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models.enums import ProjectStatus, WorkspaceRole
from app.models.project import Project
from app.models.user import User
from app.repositories.projects import ProjectsRepository
from app.repositories.sources import SourcesRepository
from app.repositories.workspaces import WorkspacesRepository
from app.schemas.dashboard import DashboardStats, RecentSourceItem
from app.schemas.project import (
    ProjectCreate,
    ProjectRead,
    ProjectSummary,
    ProjectUpdate,
    RepositoryRead,
)
from app.services import audit_service
from app.services.workspace_service import WorkspaceService


class ProjectService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.projects = ProjectsRepository(db)
        self.sources = SourcesRepository(db)
        self.workspaces = WorkspacesRepository(db)

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------
    def create(self, user: User, payload: ProjectCreate, *, role: WorkspaceRole) -> ProjectRead:
        project = self.projects.create(
            workspace_id=payload.workspace_id,
            name=payload.name,
            description=payload.description,
            departing_role=payload.departing_role,
            successor_role=payload.successor_role,
            status=payload.status,
        )
        self.db.commit()
        self.db.refresh(project)

        audit_service.record(
            self.db,
            action="project.created",
            user_id=user.id,
            workspace_id=project.workspace_id,
            resource_type="project",
            resource_id=project.id,
            metadata={"name": project.name},
        )
        return self.to_read(project, role=role)

    def update(
        self, project: Project, payload: ProjectUpdate, *, user: User, role: WorkspaceRole
    ) -> ProjectRead:
        data = payload.model_dump(exclude_unset=True)
        for field, value in data.items():
            setattr(project, field, value)
        self.db.commit()
        self.db.refresh(project)

        audit_service.record(
            self.db,
            action="project.updated",
            user_id=user.id,
            workspace_id=project.workspace_id,
            resource_type="project",
            resource_id=project.id,
            metadata={"fields": sorted(data)},
        )
        return self.to_read(project, role=role)

    def delete(self, project: Project, *, user: User) -> None:
        workspace_id = project.workspace_id
        project_id = project.id
        self.db.delete(project)
        self.db.commit()

        audit_service.record(
            self.db,
            action="project.deleted",
            user_id=user.id,
            workspace_id=workspace_id,
            resource_type="project",
            resource_id=project_id,
            metadata={},
        )

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------
    def list(
        self,
        user: User,
        *,
        workspace_id: uuid.UUID | None = None,
        search: str | None = None,
        status: ProjectStatus | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ProjectSummary], int]:
        if workspace_id is not None:
            workspace_ids = [workspace_id]
        else:
            workspace_ids = [
                workspace.id for workspace, _ in self.workspaces.list_for_user(user.id)
            ]
        if not workspace_ids:
            return [], 0

        offset = max(page - 1, 0) * page_size
        projects, total = self.projects.list_for_workspace(
            workspace_ids, search=search, status=status, limit=page_size, offset=offset
        )
        ids = [project.id for project in projects]
        source_counts = self.projects.source_counts_by_project(ids)
        repository_counts = self.projects.repository_counts_by_project(ids)

        return (
            [
                self.to_summary(
                    project,
                    source_count=source_counts.get(project.id, 0),
                    repository_count=repository_counts.get(project.id, 0),
                )
                for project in projects
            ],
            total,
        )

    def to_summary(
        self, project: Project, *, source_count: int | None = None, repository_count: int | None = None
    ) -> ProjectSummary:
        return ProjectSummary(
            id=project.id,
            workspace_id=project.workspace_id,
            name=project.name,
            description=project.description,
            status=project.status,
            departing_role=project.departing_role,
            successor_role=project.successor_role,
            created_at=project.created_at,
            updated_at=project.updated_at,
            source_count=(
                self.projects.source_count(project.id) if source_count is None else source_count
            ),
            repository_count=(
                self.projects.repository_count(project.id)
                if repository_count is None
                else repository_count
            ),
        )

    def to_read(self, project: Project, *, role: WorkspaceRole | None = None) -> ProjectRead:
        summary = self.to_summary(project)
        workspace = self.workspaces.get(project.workspace_id)
        workspace_summary = (
            WorkspaceService(self.db).to_summary(workspace, role=role) if workspace else None
        )
        repositories = [
            RepositoryRead.model_validate(link)
            for link in self.projects.list_repositories(project.id)
        ]
        return ProjectRead(
            **summary.model_dump(),
            workspace=workspace_summary,
            repositories=repositories,
            source_type_counts=self.sources.counts_by_type(project.id),
            processing_status_counts=self.sources.counts_by_status(project.id),
        )

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------
    def dashboard(self, user: User) -> DashboardStats:
        workspaces = self.workspaces.list_for_user(user.id)
        workspace_ids = [workspace.id for workspace, _ in workspaces]

        # Source aggregates are keyed by project id, not workspace id.
        all_project_ids = self.projects.all_ids_for_workspaces(workspace_ids)
        type_counts, status_counts, total_sources = self.sources.counts_for_projects(
            all_project_ids
        )
        recent_projects = self.projects.list_recent(workspace_ids, limit=5)
        project_ids = [project.id for project in recent_projects]
        source_counts = self.projects.source_counts_by_project(project_ids)
        repository_counts = self.projects.repository_counts_by_project(project_ids)

        recent_sources = [
            RecentSourceItem(
                id=source.id,
                project_id=project_id,
                project_name=project_name,
                source_type=source.source_type,
                source_name=source.source_name,
                processing_status=source.processing_status,
                created_at=source.created_at,
            )
            for source, project_id, project_name in self.sources.recent_for_workspace(
                workspace_ids, limit=8
            )
        ]

        return DashboardStats(
            total_projects=sum(
                self.workspaces.project_count(workspace.id) for workspace, _ in workspaces
            ),
            total_sources=total_sources,
            total_workspaces=len(workspaces),
            total_connected_repositories=sum(repository_counts.values()),
            source_type_counts=type_counts,
            processing_status_counts=status_counts,
            recent_projects=[
                self.to_summary(
                    project,
                    source_count=source_counts.get(project.id, 0),
                    repository_count=repository_counts.get(project.id, 0),
                )
                for project in recent_projects
            ],
            recent_sources=recent_sources,
        )
