"""add variation strategy to generation runs

Diversity was purely seed-based; a run had no record of which instance
strategy produced it. The column persists the requested ``variation``
(random / best / minimize-teacher-gaps / minimize-student-gaps) so the
async worker, which re-resolves the run row, applies the same strategy
the client asked for.

Revision ID: b4f1c9d3e7a2
Revises: e9f4a2b6d8c0
Create Date: 2026-08-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b4f1c9d3e7a2"
down_revision: Union[str, Sequence[str], None] = "e9f4a2b6d8c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    variationmode = sa.Enum(
        "RANDOM",
        "BEST",
        "MINIMIZE_TEACHER_GAPS",
        "MINIMIZE_STUDENT_GAPS",
        name="variationmode",
    )
    variationmode.create(op.get_bind(), checkfirst=False)
    op.add_column(
        "timetable_generations",
        sa.Column(
            "variation",
            variationmode,
            nullable=False,
            server_default="RANDOM",
        ),
    )


def downgrade() -> None:
    op.drop_column("timetable_generations", "variation")
    op.execute("DROP TYPE IF EXISTS variationmode")
