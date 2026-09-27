"""add incident verification tokens

Revision ID: b2f4a7c91d3e
Revises: f3c8a1d92b70
Create Date: 2026-09-27 17:30:00.000000

Single-use, signed tokens proving a flagged (AUTO_FLAG) incident's report is
genuine - api/verification.py. One additive table, `jti` (the JWT id) as its
primary key, `used`/`used_at` tracking consumption so a valid signature can
still only verify a report once.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b2f4a7c91d3e'
down_revision: Union[str, Sequence[str], None] = 'f3c8a1d92b70'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'incident_verification_tokens',
        sa.Column('jti', sa.String(), nullable=False),
        sa.Column('incident_id', sa.String(), nullable=False),
        sa.Column('issued_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('issued_by', sa.String(), nullable=False),
        sa.Column('used', sa.Boolean(), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('used_from_ip', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['incident_id'], ['incidents.incident_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('jti'),
    )
    op.create_index(
        op.f('ix_incident_verification_tokens_incident_id'),
        'incident_verification_tokens', ['incident_id'], unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f('ix_incident_verification_tokens_incident_id'),
        table_name='incident_verification_tokens',
    )
    op.drop_table('incident_verification_tokens')
