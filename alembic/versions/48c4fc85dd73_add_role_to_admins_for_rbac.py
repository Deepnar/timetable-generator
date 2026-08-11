"""add role to admins for RBAC

Revision ID: 48c4fc85dd73
Revises: 1d8688977519
Create Date: 2026-08-11 01:02:11.672939

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '48c4fc85dd73'
down_revision: Union[str, Sequence[str], None] = '1d8688977519'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add a role column to admins, defaulting to 'admin' so existing rows
    and the self-registration path keep working (DD-021 RBAC)."""
    role_type = postgresql.ENUM('admin', 'hod', 'teacher', 'student',
                                name='adminrole')
    role_type.create(op.get_bind(), checkfirst=True)
    op.add_column(
        'admins',
        sa.Column('role', role_type, nullable=False,
                  server_default='admin'),
    )


def downgrade() -> None:
    """Drop the role column (the enum type is left in place for simplicity)."""
    op.drop_column('admins', 'role')
