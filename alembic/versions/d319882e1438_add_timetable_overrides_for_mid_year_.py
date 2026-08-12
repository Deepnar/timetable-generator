"""add timetable_overrides for mid-year changes

Revision ID: d319882e1438
Revises: 48c4fc85dd73
Create Date: 2026-08-12 15:32:13.071412

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd319882e1438'
down_revision: Union[str, Sequence[str], None] = '48c4fc85dd73'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the mid-year change exception table (DD-026)."""
    override_type = postgresql.ENUM(
        'TEACHER_COVER', 'ROOM_CHANGE', 'SWAP', 'TEMP', 'CUSTOM',
        name='overridetype')
    op.create_table(
        'timetable_overrides',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('instance_id', sa.Integer(), nullable=False),
        sa.Column('slot_id', sa.Integer(), nullable=True),
        sa.Column('override_type', override_type, nullable=False),
        sa.Column('date_from', sa.Date(), nullable=True),
        sa.Column('date_to', sa.Date(), nullable=True),
        sa.Column('new_faculty_id', sa.Integer(), nullable=True),
        sa.Column('new_room_id', sa.Integer(), nullable=True),
        sa.Column('swap_with_slot_id', sa.Integer(), nullable=True),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['admins.id'], ),
        sa.ForeignKeyConstraint(
            ['instance_id'], ['timetable_instances.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(
            ['new_faculty_id'], ['faculty.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(
            ['new_room_id'], ['rooms.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(
            ['slot_id'], ['timetable_slots.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(
            ['swap_with_slot_id'], ['timetable_slots.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Drop the change table (the enum type is left in place for simplicity)."""
    op.drop_table('timetable_overrides')
