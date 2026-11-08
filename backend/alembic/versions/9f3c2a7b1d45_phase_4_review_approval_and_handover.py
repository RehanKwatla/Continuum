"""phase 4 human review, approval and versioned handover

Revision ID: 9f3c2a7b1d45
Revises: 52e47b4633ae
Create Date: 2026-11-09 09:12:03.118442

Adds the human-review, approval and versioned-handover persistence:

* ``claim_revisions`` / ``claim_decisions`` — a claim's statement can be
  corrected by a reviewer without silently inheriting its old evidence
  verification, and every human decision is recorded against one exact revision;
* ``handovers`` / ``handover_versions`` — the logical handover plus its
  immutable, individually reviewable versions. A published version is never
  overwritten;
* ``claims.revision_number`` and the widened claim-status columns (the new
  "Pending Review" / "Needs Clarification" states are longer than the original
  ``VARCHAR(16)``);
* ``conflicts.resolution`` / ``conflicts.resolution_metadata`` — the reviewer's
  chosen resolution stored *alongside* the contradiction, never replacing it.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '9f3c2a7b1d45'
down_revision: Union[str, Sequence[str], None] = '52e47b4633ae'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

#: The claim-status enum members reachable after Phase 4 ("Needs Clarification"
#: is 19 characters, which is why the backing column has to be widened).
_CLAIM_STATUS = ('Extracted', 'Supported', 'Uncertain', 'Conflict', 'Pending Review',
                 'Needs Clarification', 'Rejected', 'Verified')
_CLAIM_TYPE = ('decision', 'responsibility', 'ownership', 'task', 'unfinished_work',
               'risk', 'dependency', 'technical_constraint', 'operational_procedure',
               'open_question', 'architecture', 'process', 'constraint', 'contact',
               'status', 'other')
_REVIEW_DECISION = ('approve', 'reject', 'clarification', 'request_evidence')
_HANDOVER_LIFECYCLE = ('Draft', 'In Review', 'Approved', 'Published', 'Archived')


def upgrade() -> None:
    """Upgrade schema."""
    # -- widened claim-status columns (VARCHAR-backed enums) ------------------
    for table, column in (
        ('claims', 'status'),
        ('claim_history', 'from_status'),
        ('claim_history', 'to_status'),
    ):
        op.alter_column(
            table,
            column,
            existing_type=sa.Enum(*_CLAIM_STATUS[:4], name='claim_status', native_enum=False, length=16),
            type_=sa.Enum(*_CLAIM_STATUS, name='claim_status', native_enum=False, length=24),
            existing_nullable=not (table == 'claims'),
        )

    # -- claim revision counter ---------------------------------------------
    op.add_column(
        'claims',
        sa.Column('revision_number', sa.Integer(), server_default='1', nullable=False),
    )

    # -- conflict resolution (stored beside the contradiction) ---------------
    op.add_column('conflicts', sa.Column('resolution', sa.String(length=48), nullable=True))
    op.add_column(
        'conflicts',
        sa.Column(
            'resolution_metadata',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )

    # -- claim revisions -----------------------------------------------------
    op.create_table(
        'claim_revisions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('claim_id', sa.UUID(), nullable=False),
        sa.Column('revision_number', sa.Integer(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('claim_type', sa.Enum(*_CLAIM_TYPE, name='claim_type', native_enum=False, length=32), nullable=False),
        sa.Column('entity', sa.String(length=300), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('created_by_id', sa.UUID(), nullable=True),
        sa.Column('is_material', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('verification_required', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('verification_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['claim_id'], ['claims.id'], name=op.f('fk_claim_revisions_claim_id_claims'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_claim_revisions_created_by_id_users'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['verification_id'], ['verifications.id'], name=op.f('fk_claim_revisions_verification_id_verifications'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_claim_revisions')),
        sa.UniqueConstraint('claim_id', 'revision_number', name='uq_claim_revisions_claim_revision'),
    )
    op.create_index(op.f('ix_claim_revisions_claim_id'), 'claim_revisions', ['claim_id'], unique=False)
    op.create_index(op.f('ix_claim_revisions_created_by_id'), 'claim_revisions', ['created_by_id'], unique=False)
    op.create_index('ix_claim_revisions_claim_created', 'claim_revisions', ['claim_id', 'created_at'], unique=False)

    # -- claim decisions -----------------------------------------------------
    op.create_table(
        'claim_decisions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('project_id', sa.UUID(), nullable=False),
        sa.Column('claim_id', sa.UUID(), nullable=False),
        sa.Column('claim_revision_id', sa.UUID(), nullable=True),
        sa.Column('reviewer_id', sa.UUID(), nullable=True),
        sa.Column('decision', sa.Enum(*_REVIEW_DECISION, name='review_decision', native_enum=False, length=32), nullable=False),
        sa.Column('explanation', sa.Text(), nullable=True),
        sa.Column('from_status', sa.String(length=24), nullable=True),
        sa.Column('to_status', sa.String(length=24), nullable=True),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['claim_id'], ['claims.id'], name=op.f('fk_claim_decisions_claim_id_claims'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['claim_revision_id'], ['claim_revisions.id'], name=op.f('fk_claim_decisions_claim_revision_id_claim_revisions'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_claim_decisions_project_id_projects'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['reviewer_id'], ['users.id'], name=op.f('fk_claim_decisions_reviewer_id_users'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_claim_decisions')),
    )
    op.create_index(op.f('ix_claim_decisions_claim_id'), 'claim_decisions', ['claim_id'], unique=False)
    op.create_index(op.f('ix_claim_decisions_claim_revision_id'), 'claim_decisions', ['claim_revision_id'], unique=False)
    op.create_index(op.f('ix_claim_decisions_decision'), 'claim_decisions', ['decision'], unique=False)
    op.create_index(op.f('ix_claim_decisions_project_id'), 'claim_decisions', ['project_id'], unique=False)
    op.create_index(op.f('ix_claim_decisions_reviewer_id'), 'claim_decisions', ['reviewer_id'], unique=False)
    op.create_index('ix_claim_decisions_claim_created', 'claim_decisions', ['claim_id', 'created_at'], unique=False)
    op.create_index('ix_claim_decisions_project_decision', 'claim_decisions', ['project_id', 'decision'], unique=False)

    # -- handovers -----------------------------------------------------------
    op.create_table(
        'handovers',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('project_id', sa.UUID(), nullable=False),
        sa.Column('title', sa.String(length=300), nullable=False),
        sa.Column('status', sa.Enum(*_HANDOVER_LIFECYCLE, name='handover_lifecycle_status', native_enum=False, length=16), server_default='Draft', nullable=False),
        sa.Column('current_version', sa.Integer(), server_default='0', nullable=False),
        sa.Column('created_by_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_handovers_created_by_id_users'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_handovers_project_id_projects'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_handovers')),
    )
    op.create_index(op.f('ix_handovers_project_id'), 'handovers', ['project_id'], unique=False)
    op.create_index(op.f('ix_handovers_created_by_id'), 'handovers', ['created_by_id'], unique=False)
    op.create_index(op.f('ix_handovers_status'), 'handovers', ['status'], unique=False)
    op.create_index('ix_handovers_project_created', 'handovers', ['project_id', 'created_at'], unique=False)

    # -- handover versions ---------------------------------------------------
    op.create_table(
        'handover_versions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('handover_id', sa.UUID(), nullable=False),
        sa.Column('version_number', sa.Integer(), nullable=False),
        sa.Column('document_id', sa.UUID(), nullable=True),
        sa.Column('structured_content', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('included_claim_ids', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('claim_revisions', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('validation_errors', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('reviewer_notes', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('status', sa.Enum(*_HANDOVER_LIFECYCLE, name='handover_lifecycle_status', native_enum=False, length=16), server_default='Draft', nullable=False),
        sa.Column('generated_by_id', sa.UUID(), nullable=True),
        sa.Column('approved_by_id', sa.UUID(), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('model_name', sa.String(length=120), nullable=True),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['approved_by_id'], ['users.id'], name=op.f('fk_handover_versions_approved_by_id_users'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['document_id'], ['handover_documents.id'], name=op.f('fk_handover_versions_document_id_handover_documents'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['generated_by_id'], ['users.id'], name=op.f('fk_handover_versions_generated_by_id_users'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['handover_id'], ['handovers.id'], name=op.f('fk_handover_versions_handover_id_handovers'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_handover_versions')),
        sa.UniqueConstraint('handover_id', 'version_number', name='uq_handover_versions_handover_version'),
    )
    op.create_index(op.f('ix_handover_versions_handover_id'), 'handover_versions', ['handover_id'], unique=False)
    op.create_index(op.f('ix_handover_versions_status'), 'handover_versions', ['status'], unique=False)
    op.create_index('ix_handover_versions_handover_created', 'handover_versions', ['handover_id', 'created_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_handover_versions_handover_created', table_name='handover_versions')
    op.drop_index(op.f('ix_handover_versions_status'), table_name='handover_versions')
    op.drop_index(op.f('ix_handover_versions_handover_id'), table_name='handover_versions')
    op.drop_table('handover_versions')

    op.drop_index('ix_handovers_project_created', table_name='handovers')
    op.drop_index(op.f('ix_handovers_status'), table_name='handovers')
    op.drop_index(op.f('ix_handovers_created_by_id'), table_name='handovers')
    op.drop_index(op.f('ix_handovers_project_id'), table_name='handovers')
    op.drop_table('handovers')

    op.drop_index('ix_claim_decisions_project_decision', table_name='claim_decisions')
    op.drop_index('ix_claim_decisions_claim_created', table_name='claim_decisions')
    op.drop_index(op.f('ix_claim_decisions_reviewer_id'), table_name='claim_decisions')
    op.drop_index(op.f('ix_claim_decisions_project_id'), table_name='claim_decisions')
    op.drop_index(op.f('ix_claim_decisions_decision'), table_name='claim_decisions')
    op.drop_index(op.f('ix_claim_decisions_claim_revision_id'), table_name='claim_decisions')
    op.drop_index(op.f('ix_claim_decisions_claim_id'), table_name='claim_decisions')
    op.drop_table('claim_decisions')

    op.drop_index('ix_claim_revisions_claim_created', table_name='claim_revisions')
    op.drop_index(op.f('ix_claim_revisions_created_by_id'), table_name='claim_revisions')
    op.drop_index(op.f('ix_claim_revisions_claim_id'), table_name='claim_revisions')
    op.drop_table('claim_revisions')

    op.drop_column('conflicts', 'resolution_metadata')
    op.drop_column('conflicts', 'resolution')
    op.drop_column('claims', 'revision_number')

    for table, column, nullable in (
        ('claim_history', 'to_status', True),
        ('claim_history', 'from_status', True),
        ('claims', 'status', False),
    ):
        op.alter_column(
            table,
            column,
            existing_type=sa.Enum(*_CLAIM_STATUS, name='claim_status', native_enum=False, length=24),
            type_=sa.Enum(*_CLAIM_STATUS[:4], name='claim_status', native_enum=False, length=16),
            existing_nullable=nullable,
        )
