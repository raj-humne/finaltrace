"""add analyst feedback loop tables (Challenge 2)

Revision ID: f3c8a1d92b70
Revises: a86e95be8a23
Create Date: 2026-09-27 16:00:00.000000

Hand-written, following 2844566c110f's pattern: four new additive tables
(analyst_feedback, behavioral_baselines, edge_feedback_weights,
feature_observations) plus four new nullable columns on `incidents`
(disposition, disposition_reason, dismissed_at, dismissed_by) - a plain
ADD COLUMN sequence, safe on SQLite since none of these are primary-key or
NOT NULL changes.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f3c8a1d92b70'
down_revision: Union[str, Sequence[str], None] = 'a86e95be8a23'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'analyst_feedback',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('incident_id', sa.String(), nullable=False),
        sa.Column('analyst_id', sa.String(), nullable=False),
        sa.Column('verdict', sa.String(), nullable=False),
        sa.Column('reason_code', sa.String(), nullable=False),
        sa.Column('comment', sa.String(), nullable=True),
        sa.Column('apply_to_similar', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("verdict IN ('false_positive')", name='ck_analyst_feedback_verdict'),
        sa.CheckConstraint(
            "reason_code IN ("
            "'approved_business_activity','expected_off_hours_work','known_usb_workflow',"
            "'known_host_access','expected_bulk_access','test_or_training','other')",
            name='ck_analyst_feedback_reason_code',
        ),
        sa.ForeignKeyConstraint(['incident_id'], ['incidents.incident_id'], ),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'behavioral_baselines',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('entity_type', sa.String(), nullable=False),
        sa.Column('entity_id', sa.String(), nullable=False),
        sa.Column('feature_name', sa.String(), nullable=False),
        sa.Column('mean_value', sa.Float(), nullable=False),
        sa.Column('std_value', sa.Float(), nullable=False),
        sa.Column('p95_value', sa.Float(), nullable=False),
        sa.Column('sample_count', sa.Integer(), nullable=False),
        sa.Column('feedback_adjustment', sa.Float(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'entity_type', 'entity_id', 'feature_name', name='uq_behavioral_baseline_entity_feature'
        ),
    )

    op.create_table(
        'edge_feedback_weights',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('source_event_type', sa.String(), nullable=False),
        sa.Column('target_event_type', sa.String(), nullable=False),
        sa.Column('context_key', sa.String(), nullable=False),
        sa.Column('original_weight', sa.Float(), nullable=False),
        sa.Column('current_weight', sa.Float(), nullable=False),
        sa.Column('false_positive_count', sa.Integer(), nullable=False),
        sa.Column('last_feedback_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'source_event_type', 'target_event_type', 'context_key',
            name='uq_edge_feedback_weight_pair_context',
        ),
    )

    op.create_table(
        'feature_observations',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('entity_type', sa.String(), nullable=False),
        sa.Column('entity_id', sa.String(), nullable=False),
        sa.Column('feature_name', sa.String(), nullable=False),
        sa.Column('feature_value', sa.Float(), nullable=False),
        sa.Column('observed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('source_incident_id', sa.String(), nullable=True),
        sa.Column('is_trusted', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['source_incident_id'], ['incidents.incident_id'], ),
        sa.PrimaryKeyConstraint('id'),
    )

    op.add_column('incidents', sa.Column('disposition', sa.String(), nullable=True))
    op.add_column('incidents', sa.Column('disposition_reason', sa.String(), nullable=True))
    op.add_column('incidents', sa.Column('dismissed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('incidents', sa.Column('dismissed_by', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('incidents', 'dismissed_by')
    op.drop_column('incidents', 'dismissed_at')
    op.drop_column('incidents', 'disposition_reason')
    op.drop_column('incidents', 'disposition')

    op.drop_table('feature_observations')
    op.drop_table('edge_feedback_weights')
    op.drop_table('behavioral_baselines')
    op.drop_table('analyst_feedback')
