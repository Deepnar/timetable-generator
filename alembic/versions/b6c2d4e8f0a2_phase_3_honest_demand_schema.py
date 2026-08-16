"""phase 3: assignment source provenance, faculty competency, feasibility report

Three schema changes for "honest demand and honest allocation" (A3/A9/A4):

- ``subject_assignments.source`` — provenance tag (GRID | SCHEME | AUTOFILL)
  so a generated timetable can say which rows rest on real grid data.
- ``faculty_subject_competency`` — the qualified-teacher relation (faculty x
  subject) that auto-fill and ``_lab_batch_faculty`` must respect, so nobody
  is handed a practical they have never taught (B4).
- ``timetable_generations.feasibility_report`` — the pre-solve
  demand-vs-capacity report (A4), computed before the solver runs.

Revision ID: b6c2d4e8f0a2
Revises: a1b3c5d7e9f1
Create Date: 2026-08-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b6c2d4e8f0a2'
down_revision: Union[str, Sequence[str], None] = 'a1b3c5d7e9f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('subject_assignments', sa.Column('source', sa.String(10),
                                                   nullable=True))
    op.add_column('timetable_generations',
                  sa.Column('feasibility_report', sa.JSON(), nullable=True))
    op.create_table(
        'faculty_subject_competency',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('faculty_id', sa.Integer(),
                  sa.ForeignKey('faculty.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('subject_id', sa.Integer(),
                  sa.ForeignKey('subjects.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('preference_weight', sa.Float(), nullable=True),
        sa.UniqueConstraint('faculty_id', 'subject_id',
                            name='uq_faculty_subject_competency'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('faculty_subject_competency')
    op.drop_column('timetable_generations', 'feasibility_report')
    op.drop_column('subject_assignments', 'source')
