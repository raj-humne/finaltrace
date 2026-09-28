"""add missing incident_id/user_id FK indexes (fix slow live-demo wipe, again)

Revision ID: d4e6f19a3c5b
Revises: c7a1e5d3f082
Create Date: 2026-09-28 02:10:00.000000

api/live_demo.py's _wipe_demo_rows runs a DELETE (or a SELECT feeding one)
against incidents.user_id, reviews.incident_id, suppressions.source_review,
analyst_feedback.incident_id, and feature_observations.source_incident_id on
every single live-demo injection. None of these five columns were ever
indexed - c7a1e5d3f082 covered events/signals/campaigns, but the analyst
feedback loop and verification-token tables landed after that migration and
were never revisited. Profiled directly: as those tables accumulated rows
from ordinary testing, _wipe_demo_rows alone grew to 43 of a 52-second
"run live demo" call, almost entirely spent in full-table-scanning DELETEs.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd4e6f19a3c5b'
down_revision: Union[str, Sequence[str], None] = 'c7a1e5d3f082'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(op.f('ix_incidents_user_id'), 'incidents', ['user_id'], unique=False)
    op.create_index(op.f('ix_reviews_incident_id'), 'reviews', ['incident_id'], unique=False)
    op.create_index(op.f('ix_suppressions_source_review'), 'suppressions', ['source_review'], unique=False)
    op.create_index(op.f('ix_analyst_feedback_incident_id'), 'analyst_feedback', ['incident_id'], unique=False)
    op.create_index(
        op.f('ix_feature_observations_source_incident_id'), 'feature_observations', ['source_incident_id'], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_feature_observations_source_incident_id'), table_name='feature_observations')
    op.drop_index(op.f('ix_analyst_feedback_incident_id'), table_name='analyst_feedback')
    op.drop_index(op.f('ix_suppressions_source_review'), table_name='suppressions')
    op.drop_index(op.f('ix_reviews_incident_id'), table_name='reviews')
    op.drop_index(op.f('ix_incidents_user_id'), table_name='incidents')
