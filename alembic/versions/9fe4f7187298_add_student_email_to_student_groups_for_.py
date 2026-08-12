"""add student_email to student_groups for the student portal

Student-portal accounts (DD-022 #1) need to resolve to a group so /my-timetable
can show that group's published timetable. The column mirrors the existing
incharge_email link and is nullable so existing rows and CSV imports are
untouched.

Revision ID: 9fe4f7187298
Revises: d319882e1438
Create Date: 2026-08-12 16:37:52.056381

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9fe4f7187298'
down_revision: Union[str, Sequence[str], None] = 'd319882e1438'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "student_groups",
        sa.Column("student_email", sa.String(length=100), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("student_groups", "student_email")
