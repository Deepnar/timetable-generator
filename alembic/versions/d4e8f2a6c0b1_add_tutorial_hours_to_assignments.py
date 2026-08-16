"""add tutorial_hours to subject assignments

Phase 5 (DD-046): a subject can run as two streams — lectures AND tutorials
("M-III" 4x + "M-III TuT" 3x). The grid's TUTORIAL cells were folded into
the assignment's weekly_hours and every hour expanded as a LECTURE session,
so SAME_SUBJECT_SAME_DAY (at most one LECTURE per day) needed one distinct
day per hour — 7 hours on a 5-day week left 2 sessions unplaced per subject
on IT-SE-C, while the college's own grid puts a lecture and a tutorial of
the same subject on the same day. ``tutorial_hours`` carries the split; the
solver expands the tutorial stream as TUTORIAL sessions, which the rule
exempts.

Revision ID: d4e8f2a6c0b1
Revises: c9d4e8f2a6b0
Create Date: 2026-08-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e8f2a6c0b1'
down_revision: Union[str, Sequence[str], None] = 'c9d4e8f2a6b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('subject_assignments',
                  sa.Column('tutorial_hours', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('subject_assignments', 'tutorial_hours')
