"""add block_length to assignments and window_key to slots

Phase 2 (A1) promotes the lab window to a first-class unit: a window is
(group_id, period_number) and its members are (batch_number, subject_id,
faculty_id) rows sharing that period. Two new columns carry the window's
shape through to placement:

- ``subject_assignments.block_length`` — the window's slot span, read from
  the published grid (1 = the common case, 2 = a merged 2-period practical).
- ``timetable_slots.window_key`` — the window identity stamped on every batch
  slot when placed, so the constraint checker can recognise siblings of the
  same window without requiring the same subject.

Revision ID: a1b3c5d7e9f1
Revises: f7b2c8d4e1a3
Create Date: 2026-08-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b3c5d7e9f1'
down_revision: Union[str, Sequence[str], None] = 'f7b2c8d4e1a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('subject_assignments', sa.Column('block_length', sa.Integer(),
                                                   nullable=True))
    op.add_column('timetable_slots', sa.Column('window_key', sa.String(64),
                                               nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('timetable_slots', 'window_key')
    op.drop_column('subject_assignments', 'block_length')
