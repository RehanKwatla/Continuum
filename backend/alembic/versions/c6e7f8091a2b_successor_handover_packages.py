"""Persist snapshot-bound Stage 6 successor handover versions."""
from alembic import op

revision = "c6e7f8091a2b"
down_revision = "b5d6e7f8091a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    import app.models  # noqa: F401
    from app.db.base import Base
    Base.metadata.create_all(
        op.get_bind(),
        tables=[Base.metadata.tables[name] for name in ("successor_handover_packages", "successor_handover_verifications")],
        checkfirst=True,
    )


def downgrade() -> None:
    import app.models  # noqa: F401
    from app.db.base import Base
    Base.metadata.drop_all(
        op.get_bind(),
        tables=[Base.metadata.tables[name] for name in ("successor_handover_verifications", "successor_handover_packages")],
        checkfirst=True,
    )
