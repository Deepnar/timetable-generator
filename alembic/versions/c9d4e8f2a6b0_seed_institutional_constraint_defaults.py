"""seed college-default institutional constraint rows

Phase 3b (A10): the old STRUCTURAL_RULES list mixed physics with policy, so
SAME_SUBJECT_SAME_DAY and MAX_ONE_LAB_PER_DAY were always-on AND unreachable
through the API. Institutional rules now fire only from a profile or
college-default ``hard_constraints`` row (``profile_id`` NULL = college-wide
default). This migration seeds the defaults that preserve pre-Phase-3b
behaviour so nothing changes silently on an existing database; a registrar
can then edit or disable the rows through the API.

Only the three rules that were always-on are seeded. The faculty caps and
ROOM_CAPACITY_SUFFICIENT compare quantities the importer invents (D6), so
they stay off until a college row re-enables them with real numbers.

Revision ID: c9d4e8f2a6b0
Revises: b6c2d4e8f0a2
Create Date: 2026-08-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9d4e8f2a6b0'
down_revision: Union[str, Sequence[str], None] = 'b6c2d4e8f0a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The policy defaults that were always-on before Phase 3b, as
# (constraint_type, config_json, description). Keys must match
# DEFAULT_INSTITUTIONAL_CONFIGS in app/engine/constraint_registry.py.
_SEEDS = [
    (
        "SAME_SUBJECT_SAME_DAY",
        "{}",
        "at most one LECTURE per subject per day (labs and tutorials exempt)",
    ),
    (
        "MAX_ONE_LAB_PER_DAY",
        "{}",
        "max one practical window per day",
    ),
    (
        "CROSS_DEPT_DAILY_CAP",
        "{}",
        "max cross-dept sessions per day (cap from CollegeSettings.config_json)",
    ),
]


def upgrade() -> None:
    """Seed the college-default institutional rows (idempotent)."""
    for constraint_type, config_json, description in _SEEDS:
        op.execute(
            sa.text(
                """
                INSERT INTO hard_constraints
                    (profile_id, constraint_type, config_json,
                     description, is_active)
                SELECT NULL, :constraint_type, CAST(:config_json AS JSON),
                       :description, TRUE
                WHERE NOT EXISTS (
                    SELECT 1 FROM hard_constraints
                    WHERE profile_id IS NULL
                      AND constraint_type = :constraint_type
                )
                """
            ).bindparams(
                constraint_type=constraint_type,
                config_json=config_json,
                description=description,
            )
        )


def downgrade() -> None:
    """Remove the seeded college-default rows."""
    for constraint_type, _config, _description in _SEEDS:
        op.execute(
            sa.text(
                """
                DELETE FROM hard_constraints
                WHERE profile_id IS NULL
                  AND constraint_type = :constraint_type
                """
            ).bindparams(constraint_type=constraint_type)
        )
