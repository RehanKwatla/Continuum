"""phase 5 readiness, successor experience and evaluation

Revision ID: b1a7c4d92e08
Revises: 9f3c2a7b1d45
Create Date: 2026-11-09 11:40:00.000000

Adds the Phase 5 persistence layer:

* ``readiness_evaluations`` — one immutable, deterministic readiness snapshot.
  It stores the exact weights, the exact claim revisions and the exact
  requirement results that produced a score, so the score can always be
  re-derived and audited. No model opinion is stored here.
* ``successor_tasks`` — actionable work derived from *approved* claims; the
  origin claim is unique per project so re-deriving cannot duplicate tasks.
* ``knowledge_dependencies`` — single-person knowledge risk with a reviewer
  override, unique per (project, dependency_key).
* ``knowledge_gaps`` — missing knowledge kept visible, unique per
  (project, gap_key).
* ``evaluation_runs`` — one reproducible evaluation per run (metrics or a
  successor exercise) so runs can be compared for regressions.

Every enum is VARCHAR-backed (``native_enum=False``) to stay portable across
providers.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b1a7c4d92e08'
down_revision: Union[str, Sequence[str], None] = '9f3c2a7b1d45'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_READINESS_BAND = ('strong', 'mostly_ready', 'needs_review', 'not_ready')
_SUCCESSOR_TASK_PRIORITY = ('High', 'Medium', 'Low')
_SUCCESSOR_TASK_STATUS = ('Not Started', 'In Progress', 'Blocked', 'Completed')
_DEPENDENCY_RISK_STATUS = ('Low', 'Moderate', 'High', 'Unknown')
_GAP_CRITICALITY = ('critical', 'important', 'optional')
_KNOWLEDGE_GAP_STATUS = ('Open', 'In Progress', 'Resolved', 'Accepted Risk')
_EVALUATION_KIND = ('metrics', 'successor_exercise')


def _jsonb_default(value: str) -> sa.text:
    return sa.text(f"'{value}'::jsonb")


def upgrade() -> None:
    """Upgrade schema."""
    # -- readiness evaluations ----------------------------------------------
    op.create_table(
        'readiness_evaluations',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('project_id', sa.UUID(), nullable=False),
        sa.Column('handover_id', sa.UUID(), nullable=True),
        sa.Column('run_id', sa.UUID(), nullable=True),
        sa.Column('evaluated_by_id', sa.UUID(), nullable=True),
        sa.Column('overall_score', sa.Float(), nullable=False),
        sa.Column('band', sa.Enum(*_READINESS_BAND, name='readiness_band', native_enum=False, length=24), nullable=False),
        sa.Column('weights', postgresql.JSONB(astext_type=sa.Text()), server_default=_jsonb_default('{}'), nullable=False),
        sa.Column('dimension_scores', postgresql.JSONB(astext_type=sa.Text()), server_default=_jsonb_default('{}'), nullable=False),
        sa.Column('requirements', postgresql.JSONB(astext_type=sa.Text()), server_default=_jsonb_default('[]'), nullable=False),
        sa.Column('blockers', postgresql.JSONB(astext_type=sa.Text()), server_default=_jsonb_default('[]'), nullable=False),
        sa.Column('warnings', postgresql.JSONB(astext_type=sa.Text()), server_default=_jsonb_default('[]'), nullable=False),
        sa.Column('claim_revisions', postgresql.JSONB(astext_type=sa.Text()), server_default=_jsonb_default('{}'), nullable=False),
        sa.Column('formula', sa.Text(), nullable=True),
        sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), server_default=_jsonb_default('{}'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['evaluated_by_id'], ['users.id'], name=op.f('fk_readiness_evaluations_evaluated_by_id_users'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['handover_id'], ['handovers.id'], name=op.f('fk_readiness_evaluations_handover_id_handovers'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_readiness_evaluations_project_id_projects'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['run_id'], ['processing_runs.id'], name=op.f('fk_readiness_evaluations_run_id_processing_runs'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_readiness_evaluations')),
    )
    op.create_index(op.f('ix_readiness_evaluations_project_id'), 'readiness_evaluations', ['project_id'], unique=False)
    op.create_index(op.f('ix_readiness_evaluations_handover_id'), 'readiness_evaluations', ['handover_id'], unique=False)
    op.create_index(op.f('ix_readiness_evaluations_band'), 'readiness_evaluations', ['band'], unique=False)
    op.create_index('ix_readiness_evaluations_project_created', 'readiness_evaluations', ['project_id', 'created_at'], unique=False)

    # -- successor tasks -----------------------------------------------------
    op.create_table(
        'successor_tasks',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('project_id', sa.UUID(), nullable=False),
        sa.Column('title', sa.String(length=300), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('priority', sa.Enum(*_SUCCESSOR_TASK_PRIORITY, name='successor_task_priority', native_enum=False, length=16), server_default='Medium', nullable=False),
        sa.Column('status', sa.Enum(*_SUCCESSOR_TASK_STATUS, name='successor_task_status', native_enum=False, length=16), server_default='Not Started', nullable=False),
        sa.Column('owner', sa.String(length=255), nullable=True),
        sa.Column('completion_criteria', sa.Text(), nullable=True),
        sa.Column('supporting_claim_ids', postgresql.JSONB(astext_type=sa.Text()), server_default=_jsonb_default('[]'), nullable=False),
        sa.Column('dependency_ids', postgresql.JSONB(astext_type=sa.Text()), server_default=_jsonb_default('[]'), nullable=False),
        sa.Column('origin', sa.String(length=16), server_default='derived', nullable=False),
        sa.Column('origin_claim_id', sa.UUID(), nullable=True),
        sa.Column('created_by_id', sa.UUID(), nullable=True),
        sa.Column('updated_by_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_successor_tasks_created_by_id_users'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['origin_claim_id'], ['claims.id'], name=op.f('fk_successor_tasks_origin_claim_id_claims'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_successor_tasks_project_id_projects'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], name=op.f('fk_successor_tasks_updated_by_id_users'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_successor_tasks')),
        sa.UniqueConstraint('project_id', 'origin_claim_id', name='uq_successor_tasks_claim'),
    )
    op.create_index(op.f('ix_successor_tasks_project_id'), 'successor_tasks', ['project_id'], unique=False)
    op.create_index(op.f('ix_successor_tasks_status'), 'successor_tasks', ['status'], unique=False)
    op.create_index('ix_successor_tasks_project_status', 'successor_tasks', ['project_id', 'status'], unique=False)

    # -- knowledge dependencies ---------------------------------------------
    op.create_table(
        'knowledge_dependencies',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('project_id', sa.UUID(), nullable=False),
        sa.Column('dependency_key', sa.String(length=300), nullable=False),
        sa.Column('entity', sa.String(length=300), nullable=True),
        sa.Column('claim_ids', postgresql.JSONB(astext_type=sa.Text()), server_default=_jsonb_default('[]'), nullable=False),
        sa.Column('related_source_ids', postgresql.JSONB(astext_type=sa.Text()), server_default=_jsonb_default('[]'), nullable=False),
        sa.Column('involved_people', postgresql.JSONB(astext_type=sa.Text()), server_default=_jsonb_default('[]'), nullable=False),
        sa.Column('dependency_level', sa.Float(), server_default='0', nullable=False),
        sa.Column('risk_status', sa.Enum(*_DEPENDENCY_RISK_STATUS, name='dependency_risk_status', native_enum=False, length=16), server_default='Unknown', nullable=False),
        sa.Column('evidence_summary', sa.Text(), nullable=True),
        sa.Column('missing_backup_information', sa.Text(), nullable=True),
        sa.Column('override', postgresql.JSONB(astext_type=sa.Text()), server_default=_jsonb_default('{}'), nullable=False),
        sa.Column('computed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_knowledge_dependencies_project_id_projects'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_knowledge_dependencies')),
        sa.UniqueConstraint('project_id', 'dependency_key', name='uq_knowledge_dependencies_key'),
    )
    op.create_index(op.f('ix_knowledge_dependencies_project_id'), 'knowledge_dependencies', ['project_id'], unique=False)
    op.create_index(op.f('ix_knowledge_dependencies_risk_status'), 'knowledge_dependencies', ['risk_status'], unique=False)
    op.create_index('ix_knowledge_dependencies_project_risk', 'knowledge_dependencies', ['project_id', 'risk_status'], unique=False)

    # -- knowledge gaps ------------------------------------------------------
    op.create_table(
        'knowledge_gaps',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('project_id', sa.UUID(), nullable=False),
        sa.Column('gap_key', sa.String(length=160), nullable=False),
        sa.Column('category', sa.String(length=64), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('criticality', sa.Enum(*_GAP_CRITICALITY, name='gap_criticality', native_enum=False, length=16), server_default='important', nullable=False),
        sa.Column('related_claim_ids', postgresql.JSONB(astext_type=sa.Text()), server_default=_jsonb_default('[]'), nullable=False),
        sa.Column('related_source_ids', postgresql.JSONB(astext_type=sa.Text()), server_default=_jsonb_default('[]'), nullable=False),
        sa.Column('suggested_resolution', sa.Text(), nullable=True),
        sa.Column('status', sa.Enum(*_KNOWLEDGE_GAP_STATUS, name='knowledge_gap_status', native_enum=False, length=16), server_default='Open', nullable=False),
        sa.Column('reviewed_by_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_knowledge_gaps_project_id_projects'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['reviewed_by_id'], ['users.id'], name=op.f('fk_knowledge_gaps_reviewed_by_id_users'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_knowledge_gaps')),
        sa.UniqueConstraint('project_id', 'gap_key', name='uq_knowledge_gaps_key'),
    )
    op.create_index(op.f('ix_knowledge_gaps_project_id'), 'knowledge_gaps', ['project_id'], unique=False)
    op.create_index(op.f('ix_knowledge_gaps_status'), 'knowledge_gaps', ['status'], unique=False)
    op.create_index('ix_knowledge_gaps_project_status', 'knowledge_gaps', ['project_id', 'status'], unique=False)

    # -- evaluation runs -----------------------------------------------------
    op.create_table(
        'evaluation_runs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('project_id', sa.UUID(), nullable=True),
        sa.Column('kind', sa.Enum(*_EVALUATION_KIND, name='evaluation_kind', native_enum=False, length=24), server_default='metrics', nullable=False),
        sa.Column('dataset_version', sa.String(length=64), nullable=False),
        sa.Column('model_version', sa.String(length=120), nullable=True),
        sa.Column('configuration', postgresql.JSONB(astext_type=sa.Text()), server_default=_jsonb_default('{}'), nullable=False),
        sa.Column('metrics', postgresql.JSONB(astext_type=sa.Text()), server_default=_jsonb_default('{}'), nullable=False),
        sa.Column('failures', postgresql.JSONB(astext_type=sa.Text()), server_default=_jsonb_default('[]'), nullable=False),
        sa.Column('report', postgresql.JSONB(astext_type=sa.Text()), server_default=_jsonb_default('{}'), nullable=False),
        sa.Column('created_by_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_evaluation_runs_created_by_id_users'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_evaluation_runs_project_id_projects'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_evaluation_runs')),
    )
    op.create_index(op.f('ix_evaluation_runs_project_id'), 'evaluation_runs', ['project_id'], unique=False)
    op.create_index(op.f('ix_evaluation_runs_kind'), 'evaluation_runs', ['kind'], unique=False)
    op.create_index('ix_evaluation_runs_project_created', 'evaluation_runs', ['project_id', 'created_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_evaluation_runs_project_created', table_name='evaluation_runs')
    op.drop_index(op.f('ix_evaluation_runs_kind'), table_name='evaluation_runs')
    op.drop_index(op.f('ix_evaluation_runs_project_id'), table_name='evaluation_runs')
    op.drop_table('evaluation_runs')

    op.drop_index('ix_knowledge_gaps_project_status', table_name='knowledge_gaps')
    op.drop_index(op.f('ix_knowledge_gaps_status'), table_name='knowledge_gaps')
    op.drop_index(op.f('ix_knowledge_gaps_project_id'), table_name='knowledge_gaps')
    op.drop_table('knowledge_gaps')

    op.drop_index('ix_knowledge_dependencies_project_risk', table_name='knowledge_dependencies')
    op.drop_index(op.f('ix_knowledge_dependencies_risk_status'), table_name='knowledge_dependencies')
    op.drop_index(op.f('ix_knowledge_dependencies_project_id'), table_name='knowledge_dependencies')
    op.drop_table('knowledge_dependencies')

    op.drop_index('ix_successor_tasks_project_status', table_name='successor_tasks')
    op.drop_index(op.f('ix_successor_tasks_status'), table_name='successor_tasks')
    op.drop_index(op.f('ix_successor_tasks_project_id'), table_name='successor_tasks')
    op.drop_table('successor_tasks')

    op.drop_index('ix_readiness_evaluations_project_created', table_name='readiness_evaluations')
    op.drop_index(op.f('ix_readiness_evaluations_band'), table_name='readiness_evaluations')
    op.drop_index(op.f('ix_readiness_evaluations_handover_id'), table_name='readiness_evaluations')
    op.drop_index(op.f('ix_readiness_evaluations_project_id'), table_name='readiness_evaluations')
    op.drop_table('readiness_evaluations')
