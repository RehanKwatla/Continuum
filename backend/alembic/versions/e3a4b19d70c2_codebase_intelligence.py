"""Add snapshot-scoped code intelligence results.

Revision ID: e3a4b19d70c2
Revises: c84d18a2f901
"""
from alembic import op

revision = "e3a4b19d70c2"
down_revision = "c84d18a2f901"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Build DDL from the same metadata used by the application models.
    import app.models  # noqa: F401
    from app.db.base import Base
    names = ("code_analysis_runs", "language_statistics", "technology_detections", "code_symbols", "module_dependencies", "external_dependencies", "architecture_components", "entry_points")
    Base.metadata.create_all(op.get_bind(), tables=[Base.metadata.tables[name] for name in names], checkfirst=True)


def downgrade() -> None:
    import app.models  # noqa: F401
    from app.db.base import Base
    names = ("entry_points", "architecture_components", "external_dependencies", "module_dependencies", "code_symbols", "technology_detections", "language_statistics", "code_analysis_runs")
    Base.metadata.drop_all(op.get_bind(), tables=[Base.metadata.tables[name] for name in names], checkfirst=True)
