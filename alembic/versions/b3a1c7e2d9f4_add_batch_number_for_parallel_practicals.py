"""add batch_number to slots and subject_assignments for parallel practicals

The college runs practicals as parallel 2h sessions: a class is split into
batches (3 for FE, 2 lab groups for SE+) and every batch is in a lab at the
same time, in a different room, on a (usually) different subject. Two nullable
columns encode that:

- ``timetable_slots.batch_number`` tags which lab batch a slot belongs to
  (NULL = whole-division / non-batched session).
- ``subject_assignments.batch_number`` lets a lab subject declare one faculty
  per batch (matching the real grids, e.g. "Lab CG D1 D2 SuS/PD"); NULL keeps
  the legacy single-faculty whole-division assignment.

Revision ID: b3a1c7e2d9f4
Revises: 92a486f10bf9
Create Date: 2026-08-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3a1c7e2d9f4'
down_revision: Union[str, Sequence[str], None] = '92a486f10bf9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('timetable_slots', sa.Column('batch_number', sa.Integer(), nullable=True))
    op.add_column('subject_assignments', sa.Column('batch_number', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('subject_assignments', 'batch_number')
    op.drop_column('timetable_slots', 'batch_number')
