"""deduplicate subject_assignments and enforce one-row-per-(subject,group)

The importer's auto-fill invented a second (and sometimes third) assignment row
for a (subject, group) pair under a different subject-kind key, leaving 37 pairs
with 2-4 rows — each a different teacher, so one class was taught the same
subject by several people and the solver expanded them into overlapping
sessions. De-duplicate to the earliest row (the grid-derived one; auto-fill
runs afterwards) and then make the invariant structural with a unique index.

A whole-division row (NULL batch/period) must be unique on (subject, group)
alone. Coalescing NULLs to 0 is required because a plain unique index would
let duplicate NULL batch rows coexist (Postgres treats NULLs as distinct).

Revision ID: e6a1b7c3d9f2
Revises: c4d2e8f1a5b7
Create Date: 2026-08-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e6a1b7c3d9f2'
down_revision: Union[str, Sequence[str], None] = 'c4d2e8f1a5b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Keep the earliest row per (subject, group, batch, period) and index."""
    op.execute("""
        DELETE FROM subject_assignments a
        USING subject_assignments b
        WHERE a.id > b.id
          AND a.subject_id = b.subject_id
          AND a.group_id = b.group_id
          AND COALESCE(a.batch_number, 0) = COALESCE(b.batch_number, 0)
          AND COALESCE(a.period_number, 0) = COALESCE(b.period_number, 0)
    """)
    op.create_index(
        "uq_subject_assignments_subject_group_batch_period",
        "subject_assignments",
        ["subject_id", "group_id",
         sa.text("coalesce(batch_number, 0)"),
         sa.text("coalesce(period_number, 0)")],
        unique=True,
    )


def downgrade() -> None:
    """Drop the index; the de-duplication itself is not reverted."""
    op.drop_index(
        "uq_subject_assignments_subject_group_batch_period",
        table_name="subject_assignments",
    )
