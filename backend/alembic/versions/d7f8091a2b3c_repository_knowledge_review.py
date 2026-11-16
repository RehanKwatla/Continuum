"""Persist human review decisions for repository knowledge conflicts."""
from alembic import op

revision = "d7f8091a2b3c"
down_revision = "c6e7f8091a2b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Earlier repository migrations call metadata.create_all(). On a fresh
    # database that metadata already contains these fields; deployed databases
    # created by the older revision do not. Guard both paths explicitly.
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'repository_knowledge_conflicts' AND column_name = 'resolution_note') THEN
                ALTER TABLE repository_knowledge_conflicts ADD COLUMN resolution_note TEXT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'repository_knowledge_conflicts' AND column_name = 'reviewed_by_id') THEN
                ALTER TABLE repository_knowledge_conflicts ADD COLUMN reviewed_by_id UUID;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'repository_knowledge_conflicts' AND column_name = 'reviewed_at') THEN
                ALTER TABLE repository_knowledge_conflicts ADD COLUMN reviewed_at TIMESTAMP WITH TIME ZONE;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'repository_knowledge_conflicts' AND column_name = 'requires_reverification') THEN
                ALTER TABLE repository_knowledge_conflicts ADD COLUMN requires_reverification BOOLEAN NOT NULL DEFAULT true;
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint AS c
                JOIN pg_attribute AS a ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
                WHERE c.conrelid = 'repository_knowledge_conflicts'::regclass
                  AND c.contype = 'f' AND a.attname = 'reviewed_by_id'
            ) THEN
                ALTER TABLE repository_knowledge_conflicts ADD CONSTRAINT fk_repo_knowledge_conflicts_reviewed_by_users FOREIGN KEY (reviewed_by_id) REFERENCES users (id) ON DELETE SET NULL;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE repository_knowledge_conflicts DROP CONSTRAINT IF EXISTS fk_repo_knowledge_conflicts_reviewed_by_users")
    op.execute("ALTER TABLE repository_knowledge_conflicts DROP COLUMN IF EXISTS requires_reverification")
    op.execute("ALTER TABLE repository_knowledge_conflicts DROP COLUMN IF EXISTS reviewed_at")
    op.execute("ALTER TABLE repository_knowledge_conflicts DROP COLUMN IF EXISTS reviewed_by_id")
    op.execute("ALTER TABLE repository_knowledge_conflicts DROP COLUMN IF EXISTS resolution_note")
