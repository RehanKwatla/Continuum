"""Repository Intelligence persistence.

These tables hold the structured result of analysing a public Git repository.
They deliberately sit *beside* the existing ``Source`` / ``Evidence`` / ``Claim``
architecture rather than replacing it:

* a :class:`RepositoryConnection` is linked to a Continuum project, so a
  repository is always a source of evidence for that project;
* a :class:`RepositorySnapshot` records one immutable ingestion attempt;
* the record tables preserve provider identities (commit SHA, issue number, PR
  number, file path) so repeated ingestion is idempotent;
* ``source_id`` columns point at the normalised :class:`Source` row created for
  the same artefact, which is what the memory layer consumes. No claim is ever
  created automatically here.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import (
    ProcessingStatus,
    RepositoryIngestionStatus,
    RepositoryVisibility,
)
from app.models.types import (
    CreatedAt,
    JsonArray,
    JsonObject,
    UpdatedAt,
    UuidFK,
    UuidPK,
    sa_enum,
)


class RepositoryConnection(Base):
    """A public repository connected to one Continuum project."""

    __tablename__ = "repository_connections"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "provider",
            "owner",
            "repository_name",
            name="uq_repository_connections_project_provider_repo",
        ),
        Index("ix_repository_connections_project", "project_id"),
    )

    id: Mapped[UuidPK]
    project_id: Mapped[UuidFK] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(
        String(32), nullable=False, default="github", server_default="github"
    )
    owner: Mapped[str] = mapped_column(String(200), nullable=False)
    repository_name: Mapped[str] = mapped_column(String(200), nullable=False)
    repository_url: Mapped[str] = mapped_column(String(500), nullable=False)
    default_branch: Mapped[str | None] = mapped_column(String(200), nullable=True)
    selected_branch: Mapped[str | None] = mapped_column(String(200), nullable=True)
    visibility: Mapped[RepositoryVisibility] = mapped_column(
        sa_enum(RepositoryVisibility, "repository_visibility", length=16),
        nullable=False,
        default=RepositoryVisibility.PUBLIC,
        server_default=RepositoryVisibility.PUBLIC.value,
    )

    # --- snapshot metadata reported by the provider -------------------------
    external_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str | None] = mapped_column(String(120), nullable=True)
    languages: Mapped[JsonObject] = mapped_column(nullable=False, default=dict)
    stars: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    forks: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    open_issues: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    license_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    repository_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    repository_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    repository_pushed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    #: Branch discovery result: [{name, commit_sha, protected, is_default}, ...]
    branches: Mapped[JsonArray] = mapped_column(nullable=False, default=list)
    meta: Mapped[JsonObject] = mapped_column("metadata", nullable=False, default=dict)

    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]

    project: Mapped["Project"] = relationship()  # noqa: F821
    snapshots: Mapped[list["RepositorySnapshot"]] = relationship(
        back_populates="connection", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<RepositoryConnection {self.owner}/{self.repository_name}>"


class RepositorySnapshot(Base):
    """One ingestion attempt for one branch of a repository."""

    __tablename__ = "repository_snapshots"
    __table_args__ = (
        Index("ix_repository_snapshots_connection_branch", "repository_connection_id", "branch"),
        Index("ix_repository_snapshots_status", "ingestion_status"),
        Index(
            "uq_repository_snapshots_active_branch",
            "repository_connection_id",
            "branch",
            unique=True,
            postgresql_where=text(
                "ingestion_status IN ('queued','validating','fetching_metadata','fetching_branches',"
                "'fetching_tree','fetching_files','fetching_commits','fetching_issues',"
                "'fetching_pull_requests','saving_snapshot')"
            ),
        ),
    )

    id: Mapped[UuidPK]
    repository_connection_id: Mapped[UuidFK] = mapped_column(
        ForeignKey("repository_connections.id", ondelete="CASCADE"), index=True
    )
    requested_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    branch: Mapped[str] = mapped_column(String(200), nullable=False)
    commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ingestion_status: Mapped[RepositoryIngestionStatus] = mapped_column(
        sa_enum(RepositoryIngestionStatus, "repository_ingestion_status", length=32),
        nullable=False,
        default=RepositoryIngestionStatus.QUEUED,
        server_default=RepositoryIngestionStatus.QUEUED.value,
        index=True,
    )
    tree_complete: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    files_discovered: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    files_processed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    files_skipped: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    commits_processed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    issues_processed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    pull_requests_processed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    limits: Mapped[JsonObject] = mapped_column(nullable=False, default=dict)
    warnings: Mapped[JsonArray] = mapped_column(nullable=False, default=list)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]

    connection: Mapped[RepositoryConnection] = relationship(back_populates="snapshots")
    files: Mapped[list["RepositoryFile"]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<RepositorySnapshot {self.id} {self.branch} {self.ingestion_status}>"


class RepositoryFile(Base):
    """One file discovered in a snapshot's Git tree."""

    __tablename__ = "repository_files"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "path", name="uq_repository_files_snapshot_path"),
        Index("ix_repository_files_snapshot_extension", "snapshot_id", "extension"),
    )

    id: Mapped[UuidPK]
    snapshot_id: Mapped[UuidFK] = mapped_column(
        ForeignKey("repository_snapshots.id", ondelete="CASCADE"), index=True
    )
    path: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    directory_path: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    extension: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    file_type: Mapped[str] = mapped_column(String(32), nullable=False, default="file")
    size: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    blob_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    #: Reference to the stored/normalised content (``source:<uuid>`` today).
    content_storage_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    analysis_status: Mapped[ProcessingStatus] = mapped_column(
        sa_enum(ProcessingStatus, "processing_status", length=16),
        nullable=False,
        default=ProcessingStatus.PENDING,
        server_default=ProcessingStatus.PENDING.value,
    )
    skip_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]

    snapshot: Mapped[RepositorySnapshot] = relationship(back_populates="files")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<RepositoryFile {self.path} {self.analysis_status}>"


class CommitRecord(Base):
    """A commit read from the provider, keyed by (connection, SHA)."""

    __tablename__ = "repository_commits"
    __table_args__ = (
        UniqueConstraint(
            "repository_connection_id",
            "commit_sha",
            name="uq_repository_commits_connection_sha",
        ),
        Index("ix_repository_commits_connection_committed", "repository_connection_id", "committed_at"),
    )

    id: Mapped[UuidPK]
    repository_connection_id: Mapped[UuidFK] = mapped_column(
        ForeignKey("repository_connections.id", ondelete="CASCADE"), index=True
    )
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("repository_snapshots.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL"), nullable=True
    )
    commit_sha: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    parent_shas: Mapped[JsonArray] = mapped_column(nullable=False, default=list)
    author_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    author_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    github_author: Mapped[str | None] = mapped_column(String(200), nullable=True)
    committer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    committer_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    changed_files: Mapped[JsonArray] = mapped_column(nullable=False, default=list)
    additions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    deletions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_changes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[CreatedAt]

    def __repr__(self) -> str:  # pragma: no cover
        return f"<CommitRecord {self.commit_sha[:7]}>"


class IssueRecord(Base):
    """A public issue, keyed by (connection, issue number)."""

    __tablename__ = "repository_issues"
    __table_args__ = (
        UniqueConstraint(
            "repository_connection_id", "issue_number", name="uq_repository_issues_connection_number"
        ),
    )

    id: Mapped[UuidPK]
    repository_connection_id: Mapped[UuidFK] = mapped_column(
        ForeignKey("repository_connections.id", ondelete="CASCADE"), index=True
    )
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("repository_snapshots.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL"), nullable=True
    )
    issue_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    labels: Mapped[JsonArray] = mapped_column(nullable=False, default=list)
    assignees: Mapped[JsonArray] = mapped_column(nullable=False, default=list)
    author: Mapped[str | None] = mapped_column(String(200), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at_source: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at_source: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[CreatedAt]

    def __repr__(self) -> str:  # pragma: no cover
        return f"<IssueRecord #{self.issue_number}>"


class PullRequestRecord(Base):
    """A public pull request, keyed by (connection, PR number)."""

    __tablename__ = "repository_pull_requests"
    __table_args__ = (
        UniqueConstraint(
            "repository_connection_id",
            "pr_number",
            name="uq_repository_pull_requests_connection_number",
        ),
    )

    id: Mapped[UuidPK]
    repository_connection_id: Mapped[UuidFK] = mapped_column(
        ForeignKey("repository_connections.id", ondelete="CASCADE"), index=True
    )
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("repository_snapshots.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL"), nullable=True
    )
    pr_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    author: Mapped[str | None] = mapped_column(String(200), nullable=True)
    base_branch: Mapped[str | None] = mapped_column(String(200), nullable=True)
    head_branch: Mapped[str | None] = mapped_column(String(200), nullable=True)
    merged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at_source: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at_source: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    changed_files: Mapped[JsonArray] = mapped_column(nullable=False, default=list)
    reviews: Mapped[JsonArray] = mapped_column(nullable=False, default=list)
    reviews_available: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[CreatedAt]

    def __repr__(self) -> str:  # pragma: no cover
        return f"<PullRequestRecord #{self.pr_number}>"
