"""add subject_assignments.period_number for weekly lab periods

A lab subject runs several parallel practicals per week — each a *period* with
its own batch group (TE CG: D1D2 = batches 1,2 on one day, D3D4 = batches 3,4 on
another). ``batch_number`` is a global batch id (D1..D4), so it cannot separate
periods by itself; ``period_number`` tags which weekly period a batch row
belongs to. The solver groups batched rows by (subject, group, period_number)
into one atomic parallel placement per period.

Revision ID: c4d2e8f1a5b7
Revises: b3a1c7e2d9f4
Create Date: 2026-08-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4d2e8f1a5b7'
down_revision: Union[str, Sequence[str], None] = 'b3a1c7e2d9f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('subject_assignments', sa.Column('period_number', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('subject_assignments', 'period_number')
