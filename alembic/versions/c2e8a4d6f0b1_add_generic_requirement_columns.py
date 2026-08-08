"""add generic resource requirement columns

Subjects gain a declarative ``requirements_json`` (room_types / min_capacity /
features / session_type) that supersedes the binary requires_lab when set, and
rooms gain ``equipment_json`` free-form feature tags to match against. See
app/engine/resource_requirements.py.

Revision ID: c2e8a4d6f0b1
Revises: b4f1c9d3e7a2
Create Date: 2026-08-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c2e8a4d6f0b1"
down_revision: Union[str, Sequence[str], None] = "b4f1c9d3e7a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "subjects",
        sa.Column("requirements_json", sa.JSON(), nullable=True),
    )
    op.add_column(
        "rooms",
        sa.Column("equipment_json", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("rooms", "equipment_json")
    op.drop_column("subjects", "requirements_json")
