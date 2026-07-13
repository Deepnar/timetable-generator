"""convert constraint_type columns from native enum to string

Data-driven constraint types are dispatched by a runtime registry, so the
``constraint_type`` columns become plain VARCHAR(100). This means a new rule
type never needs a schema migration (no ``ALTER TYPE ... ADD VALUE``, which
also can't run inside a transaction on PostgreSQL).

Revision ID: b7d9f2a1c3e4
Revises: e5f8a91c0d4e
Create Date: 2026-07-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "b7d9f2a1c3e4"
down_revision: str = "e5f8a91c0d4e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("hard_constraints", "soft_constraints")
_ENUM_NAME = "constrainttype"


def upgrade() -> None:
    bind = op.get_bind()
    for table in _TABLES:
        op.alter_column(
            table,
            "constraint_type",
            existing_type=postgresql.ENUM(name=_ENUM_NAME, create_type=False),
            type_=sa.String(length=100),
            existing_nullable=False,
            postgresql_using="constraint_type::text",
        )
    # The native enum type is now unused by any column.
    if bind.dialect.name == "postgresql":
        op.execute(f"DROP TYPE IF EXISTS {_ENUM_NAME}")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # Recreate the enum with the original members, then cast back.
        members = (
            "NO_TEACHER_DOUBLE_BOOK", "NO_ROOM_DOUBLE_BOOK", "NO_GROUP_DOUBLE_BOOK",
            "ROOM_CAPACITY_SUFFICIENT", "ROOM_TYPE_MATCH",
            "RESPECT_TEACHER_UNAVAILABILITY", "RESPECT_ROOM_BLACKOUT",
            "CONTIGUOUS_LAB_SLOTS", "EXAM_DATE_SEPARATION",
            "SUBJECT_TIME_PREFERENCE", "MAX_CONSECUTIVE_SAME_TEACHER",
            "TEACHER_YEAR_RESTRICTION",
            "TEACHER_PREFERS_MORNING", "AVOID_CONSECUTIVE_SAME_SUBJECT",
            "MINIMIZE_STUDENT_FREE_SLOTS", "MINIMIZE_TEACHER_FREE_SLOTS",
            "DISTRIBUTE_SUBJECTS_EVENLY", "BALANCE_TEACHER_LOAD",
        )
        values = ", ".join(f"'{m}'" for m in members)
        op.execute(f"CREATE TYPE {_ENUM_NAME} AS ENUM ({values})")
    for table in _TABLES:
        op.alter_column(
            table,
            "constraint_type",
            existing_type=sa.String(length=100),
            type_=postgresql.ENUM(name=_ENUM_NAME, create_type=False),
            existing_nullable=False,
            postgresql_using=f"constraint_type::{_ENUM_NAME}",
        )
