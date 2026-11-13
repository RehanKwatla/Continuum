"""Persist commit file changes and snapshot history insights.

Revision ID: a4c5d6e7f809
Revises: e3a4b19d70c2
"""
from alembic import op
import sqlalchemy as sa

revision = "a4c5d6e7f809"
down_revision = "e3a4b19d70c2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    import app.models  # noqa: F401
    from app.db.base import Base
    op.add_column("repository_commits", sa.Column("committer_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("repository_pull_requests", sa.Column("changed_file_count", sa.Integer(), nullable=True))
    op.add_column("repository_pull_requests", sa.Column("additions", sa.Integer(), nullable=True))
    op.add_column("repository_pull_requests", sa.Column("deletions", sa.Integer(), nullable=True))
    names = ("history_analysis_runs", "commit_file_changes", "commit_insights")
    Base.metadata.create_all(op.get_bind(), tables=[Base.metadata.tables[name] for name in names], checkfirst=True)


def downgrade() -> None:
    import app.models  # noqa: F401
    from app.db.base import Base
    names = ("commit_insights", "commit_file_changes", "history_analysis_runs")
    Base.metadata.drop_all(op.get_bind(), tables=[Base.metadata.tables[name] for name in names], checkfirst=True)
    op.drop_column("repository_pull_requests", "deletions")
    op.drop_column("repository_pull_requests", "additions")
    op.drop_column("repository_pull_requests", "changed_file_count")
    op.drop_column("repository_commits", "committer_at")
