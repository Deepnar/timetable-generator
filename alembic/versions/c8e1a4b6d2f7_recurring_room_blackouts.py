"""support recurring (weekday) room blackouts

A blackout can now be recurring (``day_of_week`` set) instead of only
date-specific, so the constraint checker can actually enforce it against the
recurring weekly templates (which carry ``day_of_week``, not calendar dates).
``date`` becomes nullable and a ``day_of_week`` column is added.

Revision ID: c8e1a4b6d2f7
Revises: b7d9f2a1c3e4
Create Date: 2026-07-13 00:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c8e1a4b6d2f7"
down_revision: str = "b7d9f2a1c3e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "room_blackouts",
        sa.Column("day_of_week", sa.Integer(), nullable=True),
    )
    op.alter_column(
        "room_blackouts", "date",
        existing_type=sa.Date(),
        nullable=True,
    )


def downgrade() -> None:
    # Rows created as recurring have no date; drop them so the NOT NULL restore
    # doesn't fail.
    op.execute("DELETE FROM room_blackouts WHERE date IS NULL")
    op.alter_column(
        "room_blackouts", "date",
        existing_type=sa.Date(),
        nullable=False,
    )
    op.drop_column("room_blackouts", "day_of_week")
