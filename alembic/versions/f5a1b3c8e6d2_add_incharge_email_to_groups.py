"""add incharge_email to student_groups

Publish-time email notifications need a contact address per class. The column
is nullable so existing rows (and CSV imports, which do not read it) are
untouched.

Revision ID: f5a1b3c8e6d2
Revises: d7a3c5e9f1b2
Create Date: 2026-08-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f5a1b3c8e6d2"
down_revision: Union[str, Sequence[str], None] = "d7a3c5e9f1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "student_groups",
        sa.Column("incharge_email", sa.String(length=100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("student_groups", "incharge_email")
