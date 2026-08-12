"""add app_notifications for dashboard alerts

In-app notifications complement the publish/change emails (DD-027): one row
per recipient Admin so every relevant person sees the event on their
dashboard even when SMTP is unconfigured.

Revision ID: 92a486f10bf9
Revises: 9fe4f7187298
Create Date: 2026-08-12 17:05:10.599203

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '92a486f10bf9'
down_revision: Union[str, Sequence[str], None] = '9fe4f7187298'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'app_notifications',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('recipient_admin_id', sa.Integer(), nullable=True),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('body', sa.Text(), nullable=True),
        sa.Column('instance_id', sa.Integer(), nullable=True),
        sa.Column('override_id', sa.Integer(), nullable=True),
        sa.Column('is_read', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ['recipient_admin_id'], ['admins.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(
            ['instance_id'], ['timetable_instances.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(
            ['override_id'], ['timetable_overrides.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('app_notifications')