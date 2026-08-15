"""add home_room_id and home_room_secondary_id to student_groups

A real division owns a venue (COMP-TE-D -> 718/608/610) and leaves it only
for practicals; the engine had no such concept, so lectures scattered across
every room in the pool (245 of 245 lecture pairs split). Phase 1 makes the
home room a hard domain for non-lab sessions (A5). Nullable FKs so generic
colleges that do not track a venue keep the legacy free-pool behaviour.

Revision ID: f7b2c8d4e1a3
Revises: e6a1b7c3d9f2
Create Date: 2026-08-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7b2c8d4e1a3'
down_revision: Union[str, Sequence[str], None] = 'e6a1b7c3d9f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('student_groups', sa.Column('home_room_id', sa.Integer(),
                                              sa.ForeignKey('rooms.id',
                                                            ondelete='SET NULL'),
                                              nullable=True))
    op.add_column('student_groups', sa.Column('home_room_secondary_id',
                                              sa.Integer(),
                                              sa.ForeignKey('rooms.id',
                                                            ondelete='SET NULL'),
                                              nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('student_groups', 'home_room_secondary_id')
    op.drop_column('student_groups', 'home_room_id')
