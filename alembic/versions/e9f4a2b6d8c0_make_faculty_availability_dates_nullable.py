"""make faculty_availability effective dates nullable

The schema treats effective_from/effective_to as optional, but the columns
were NOT NULL — creating a timeless availability window (or CSV-importing
one) failed at commit. The solver also now treats a NULL bound as "applies
for the whole term", so both must be nullable.

Revision ID: e9f4a2b6d8c0
Revises: d3f5a7c9e1b2
Create Date: 2026-08-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e9f4a2b6d8c0"
down_revision: str = "d3f5a7c9e1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("faculty_availability", "effective_from",
                    existing_type=sa.Date(), nullable=True)
    op.alter_column("faculty_availability", "effective_to",
                    existing_type=sa.Date(), nullable=True)


def downgrade() -> None:
    op.alter_column("faculty_availability", "effective_to",
                    existing_type=sa.Date(), nullable=False)
    op.alter_column("faculty_availability", "effective_from",
                    existing_type=sa.Date(), nullable=False)
