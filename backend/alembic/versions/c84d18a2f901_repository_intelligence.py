"""public repository intelligence snapshots

Revision ID: c84d18a2f901
Revises: b1a7c4d92e08
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "c84d18a2f901"
down_revision = "b1a7c4d92e08"
branch_labels = None
depends_on = None

def _json(value):
    return sa.text(f"'{value}'::jsonb")

def _timestamps():
    return [sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False)]

def upgrade():
    op.create_table("repository_connections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False, server_default="github"),
        sa.Column("owner", sa.String(200), nullable=False), sa.Column("repository_name", sa.String(200), nullable=False),
        sa.Column("repository_url", sa.String(500), nullable=False), sa.Column("default_branch", sa.String(200)), sa.Column("selected_branch", sa.String(200)),
        sa.Column("visibility", sa.String(16), nullable=False, server_default="public"), sa.Column("external_id", sa.String(64)),
        sa.Column("description", sa.Text()), sa.Column("language", sa.String(120)), sa.Column("languages", postgresql.JSONB(), nullable=False, server_default=_json("{}")),
        sa.Column("stars", sa.Integer(), nullable=False, server_default="0"), sa.Column("forks", sa.Integer(), nullable=False, server_default="0"), sa.Column("open_issues", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("license_name", sa.String(200)), sa.Column("repository_created_at", sa.DateTime(timezone=True)), sa.Column("repository_updated_at", sa.DateTime(timezone=True)), sa.Column("repository_pushed_at", sa.DateTime(timezone=True)),
        sa.Column("branches", postgresql.JSONB(), nullable=False, server_default=_json("[]")), sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default=_json("{}")), *_timestamps(),
        sa.UniqueConstraint("project_id", "provider", "owner", "repository_name", name="uq_repository_connections_project_provider_repo"))
    op.create_index("ix_repository_connections_project_id", "repository_connections", ["project_id"])
    op.create_index("ix_repository_connections_project", "repository_connections", ["project_id"])
    op.create_table("repository_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("repository_connection_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("repository_connections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("requested_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")), sa.Column("branch", sa.String(200), nullable=False), sa.Column("commit_sha", sa.String(64)),
        sa.Column("ingestion_status", sa.String(32), nullable=False, server_default="queued"), sa.Column("tree_complete", sa.Boolean(), nullable=False, server_default=sa.false()),
        *[sa.Column(n, sa.Integer(), nullable=False, server_default="0") for n in ("files_discovered", "files_processed", "files_skipped", "commits_processed", "issues_processed", "pull_requests_processed")],
        sa.Column("limits", postgresql.JSONB(), nullable=False, server_default=_json("{}")), sa.Column("warnings", postgresql.JSONB(), nullable=False, server_default=_json("[]")), sa.Column("error_summary", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)), sa.Column("completed_at", sa.DateTime(timezone=True)), *_timestamps())
    op.create_index("ix_repository_snapshots_connection_branch", "repository_snapshots", ["repository_connection_id", "branch"])
    op.create_index("ix_repository_snapshots_repository_connection_id", "repository_snapshots", ["repository_connection_id"])
    op.create_index("ix_repository_snapshots_status", "repository_snapshots", ["ingestion_status"])
    op.create_index("ix_repository_snapshots_ingestion_status", "repository_snapshots", ["ingestion_status"])
    op.create_index("uq_repository_snapshots_active_branch", "repository_snapshots", ["repository_connection_id", "branch"], unique=True,
        postgresql_where=sa.text("ingestion_status IN ('queued','validating','fetching_metadata','fetching_branches','fetching_tree','fetching_files','fetching_commits','fetching_issues','fetching_pull_requests','saving_snapshot')"))
    op.create_table("repository_files",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("repository_snapshots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("path", sa.String(1000), nullable=False), sa.Column("file_name", sa.String(255), nullable=False), sa.Column("directory_path", sa.String(1000), nullable=False, server_default=""),
        sa.Column("extension", sa.String(32), nullable=False, server_default=""), sa.Column("file_type", sa.String(32), nullable=False, server_default="file"), sa.Column("size", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("blob_sha", sa.String(64)), sa.Column("content_hash", sa.String(64)), sa.Column("content_storage_reference", sa.String(500)), sa.Column("analysis_status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("skip_reason", sa.Text()), sa.Column("source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sources.id", ondelete="SET NULL")), *_timestamps(),
        sa.UniqueConstraint("snapshot_id", "path", name="uq_repository_files_snapshot_path"))
    op.create_index("ix_repository_files_snapshot_extension", "repository_files", ["snapshot_id", "extension"])
    op.create_index("ix_repository_files_snapshot_id", "repository_files", ["snapshot_id"])
    op.create_index("ix_repository_files_content_hash", "repository_files", ["content_hash"])
    for table, ident, cols in (("repository_commits", "commit_sha", []), ("repository_issues", "issue_number", []), ("repository_pull_requests", "pr_number", [])):
        pass
    op.create_table("repository_commits", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("repository_connection_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("repository_connections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("repository_snapshots.id", ondelete="SET NULL")), sa.Column("source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sources.id", ondelete="SET NULL")),
        sa.Column("commit_sha", sa.String(64), nullable=False), sa.Column("parent_shas", postgresql.JSONB(), nullable=False, server_default=_json("[]")), sa.Column("author_name", sa.String(255)), sa.Column("author_email", sa.String(320)), sa.Column("github_author", sa.String(200)),
        sa.Column("committer_name", sa.String(255)), sa.Column("committer_email", sa.String(320)), sa.Column("message", sa.Text()), sa.Column("committed_at", sa.DateTime(timezone=True)), sa.Column("url", sa.String(500)), sa.Column("changed_files", postgresql.JSONB(), nullable=False, server_default=_json("[]")),
        sa.Column("additions", sa.Integer()), sa.Column("deletions", sa.Integer()), sa.Column("total_changes", sa.Integer()), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("repository_connection_id", "commit_sha", name="uq_repository_commits_connection_sha"))
    op.create_index("ix_repository_commits_connection_committed", "repository_commits", ["repository_connection_id", "committed_at"])
    op.create_index("ix_repository_commits_repository_connection_id", "repository_commits", ["repository_connection_id"])
    op.create_index("ix_repository_commits_snapshot_id", "repository_commits", ["snapshot_id"])
    op.create_index("ix_repository_commits_commit_sha", "repository_commits", ["commit_sha"])
    for table, number_col, constraint, extra in (
        ("repository_issues", "issue_number", "uq_repository_issues_connection_number", [sa.Column("labels", postgresql.JSONB(), nullable=False, server_default=_json("[]")), sa.Column("assignees", postgresql.JSONB(), nullable=False, server_default=_json("[]")), sa.Column("closed_at", sa.DateTime(timezone=True))]),
        ("repository_pull_requests", "pr_number", "uq_repository_pull_requests_connection_number", [sa.Column("base_branch", sa.String(200)), sa.Column("head_branch", sa.String(200)), sa.Column("merged_at", sa.DateTime(timezone=True)), sa.Column("closed_at", sa.DateTime(timezone=True)), sa.Column("changed_files", postgresql.JSONB(), nullable=False, server_default=_json("[]")), sa.Column("reviews", postgresql.JSONB(), nullable=False, server_default=_json("[]")), sa.Column("reviews_available", sa.Boolean(), nullable=False, server_default=sa.false())]),
    ):
        op.create_table(table, sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("repository_connection_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("repository_connections.id", ondelete="CASCADE"), nullable=False),
            sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("repository_snapshots.id", ondelete="SET NULL")), sa.Column("source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sources.id", ondelete="SET NULL")),
            sa.Column(number_col, sa.Integer(), nullable=False), sa.Column("title", sa.String(500), nullable=False), sa.Column("description", sa.Text()), sa.Column("state", sa.String(32), nullable=False, server_default="open"), *extra,
            sa.Column("author", sa.String(200)), sa.Column("created_at_source", sa.DateTime(timezone=True)), sa.Column("updated_at_source", sa.DateTime(timezone=True)), sa.Column("url", sa.String(500)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")), sa.UniqueConstraint("repository_connection_id", number_col, name=constraint))
        op.create_index(f"ix_{table}_repository_connection_id", table, ["repository_connection_id"])
        op.create_index(f"ix_{table}_snapshot_id", table, ["snapshot_id"])

def downgrade():
    for name in ("repository_pull_requests", "repository_issues", "repository_commits", "repository_files", "repository_snapshots", "repository_connections"):
        op.drop_table(name)
