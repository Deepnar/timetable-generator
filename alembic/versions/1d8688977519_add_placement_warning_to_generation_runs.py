"""add placement_warning to generation runs

Revision ID: 1d8688977519
Revises: f5a1b3c8e6d2
Create Date: 2026-08-11 00:26:17.772193

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1d8688977519'
down_revision: Union[str, Sequence[str], None] = 'f5a1b3c8e6d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add a nullable placement_warning column so a run that completes but
    drops sessions (oversubscribed profile, no matching room) reports it to
    the API instead of only printing to stdout."""
    op.add_column(
        "timetable_generations",
        sa.Column("placement_warning", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Drop the placement_warning column."""
    op.drop_column("timetable_generations", "placement_warning")
