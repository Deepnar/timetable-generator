"""add subject assignments and college settings tables

Revision ID: e5f8a91c0d4e
Revises: aeaadc4f2374 (or whatever current head is)
Create Date: 2026-07-04 20:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5f8a91c0d4e'
down_revision: str = 'e47081302c4e'  # Alembic will handle linking
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create college_settings table (Singleton)
    op.create_table(
        'college_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('enable_lab_batches', sa.Boolean(), server_default='false', nullable=True),
        sa.Column('allow_cross_dept_subjects', sa.Boolean(), server_default='false', nullable=True),
        sa.Column('enable_soft_constraint_scoring', sa.Boolean(), server_default='true', nullable=True),
        sa.Column('config_json', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # Create subject_assignments table (Mapping triad)
    op.create_table(
        'subject_assignments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('subject_id', sa.Integer(), nullable=False),
        sa.Column('faculty_id', sa.Integer(), nullable=True),
        sa.Column('group_id', sa.Integer(), nullable=False),
        sa.Column('weekly_hours', sa.Integer(), server_default='1', nullable=False),
        sa.Column('load_share', sa.Float(), server_default='1.0', nullable=False),
        sa.ForeignKeyConstraint(['subject_id'], ['subjects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['faculty_id'], ['faculty.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['group_id'], ['student_groups.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('subject_assignments')
    op.drop_table('college_settings')
