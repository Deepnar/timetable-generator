"""add CUSTOM to roomtype and sessiontype enums

The closed vocabularies blocked non-college use (exam halls, event spaces,
shift rosters). A CUSTOM escape hatch lets a room or a session carry a
free-form kind without another schema migration; free-form attributes hang off
the rooms.equipment_json / subjects.requirements_json JSON columns.

Revision ID: d7a3c5e9f1b2
Revises: c2e8a4d6f0b1
Create Date: 2026-08-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "d7a3c5e9f1b2"
down_revision: Union[str, Sequence[str], None] = "c2e8a4d6f0b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Postgres 15 allows ADD VALUE inside a transaction; the new label is only
    # unusable until commit, and this migration inserts no such rows.
    op.execute("ALTER TYPE roomtype ADD VALUE 'CUSTOM'")
    op.execute("ALTER TYPE sessiontype ADD VALUE 'CUSTOM'")


def downgrade() -> None:
    # Postgres cannot remove an enum label once created; the columns still
    # reference the type, so the label stays. Downgrade is a documented no-op.
    pass
