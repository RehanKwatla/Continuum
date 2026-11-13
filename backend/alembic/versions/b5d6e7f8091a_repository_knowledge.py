"""Add snapshot-scoped evidence-backed repository knowledge."""
from alembic import op

revision = "b5d6e7f8091a"
down_revision = "a4c5d6e7f809"
branch_labels = None
depends_on = None


def upgrade() -> None:
    import app.models  # noqa: F401
    from app.db.base import Base
    names = ("knowledge_analysis_runs", "knowledge_units", "knowledge_evidence", "knowledge_entities", "knowledge_relationships", "repository_knowledge_gaps", "repository_knowledge_conflicts", "repository_project_assumptions")
    Base.metadata.create_all(op.get_bind(), tables=[Base.metadata.tables[name] for name in names], checkfirst=True)


def downgrade() -> None:
    import app.models  # noqa: F401
    from app.db.base import Base
    names = ("repository_project_assumptions", "repository_knowledge_conflicts", "repository_knowledge_gaps", "knowledge_relationships", "knowledge_entities", "knowledge_evidence", "knowledge_units", "knowledge_analysis_runs")
    Base.metadata.drop_all(op.get_bind(), tables=[Base.metadata.tables[name] for name in names], checkfirst=True)
