"""add incident_events.event_id index (fix the real live-demo wipe bottleneck)

Revision ID: e7f2b84c1a09
Revises: d4e6f19a3c5b
Create Date: 2026-09-28 05:45:00.000000

The actual root cause of "run live demo" taking 60-130+ seconds, found by
tracing every individual SQL statement with timing: a single
`DELETE FROM events WHERE user_id = ?` was responsible for over 99% of the
time (121 of 122 seconds in one trace), even with zero other processes
touching the database and every relevant column already indexed.

The cause: api/db/session.py enables `PRAGMA foreign_keys=ON` on every
connection. incident_events.event_id has a foreign key to events.event_id,
but event_id is only the *second* column of incident_events' composite
primary key (incident_id, event_id) - SQLite's automatic index for that
composite key is ordered (incident_id, event_id) and cannot answer "does
any row have this event_id" without a full table scan. With foreign_keys
enforcement on, every single row deleted from `events` triggered exactly
that scan against incident_events (134,626 rows at the time this was
diagnosed) to verify no child row still referenced it - deleting ~2,400
events meant roughly 2400 x 134,626 row comparisons for FK checking alone.
A raw sqlite3 DELETE issued without PRAGMA foreign_keys=ON, against the
exact same data, took 27 milliseconds.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e7f2b84c1a09'
down_revision: Union[str, Sequence[str], None] = 'd4e6f19a3c5b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(op.f('ix_incident_events_event_id'), 'incident_events', ['event_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_incident_events_event_id'), table_name='incident_events')
