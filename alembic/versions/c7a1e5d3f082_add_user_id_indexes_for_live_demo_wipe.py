"""add user_id indexes (fix slow live-demo wipe)

Revision ID: c7a1e5d3f082
Revises: b2f4a7c91d3e
Create Date: 2026-09-28 01:10:00.000000

api/live_demo.py's _wipe_demo_rows runs DELETE FROM events/signals/campaigns
WHERE user_id = ... on every single live-demo injection. `events.user_id`,
`signals.user_id`, and `campaigns.user_id` were never indexed, so each
DELETE full-scanned the whole table - measured at 42.5s against the real,
accumulated demo.db (515K events), against ~5s for everything else in the
same call combined. That is the entire "takes a long time to appear in the
dashboard" symptom, not the detection engine (measured separately at 4.5s,
unaffected by database size).
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c7a1e5d3f082'
down_revision: Union[str, Sequence[str], None] = 'b2f4a7c91d3e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(op.f('ix_events_user_id'), 'events', ['user_id'], unique=False)
    op.create_index(op.f('ix_signals_user_id'), 'signals', ['user_id'], unique=False)
    op.create_index(op.f('ix_campaigns_user_id'), 'campaigns', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_campaigns_user_id'), table_name='campaigns')
    op.drop_index(op.f('ix_signals_user_id'), table_name='signals')
    op.drop_index(op.f('ix_events_user_id'), table_name='events')
