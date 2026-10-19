"""exercises: progression settings for the overload targets (E33)

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-19 18:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = (
    ("rep_min", sa.Integer()),
    ("rep_max", sa.Integer()),
    ("weight_step", sa.Float()),
    ("sets_max", sa.Integer()),
)


def upgrade() -> None:
    for name, type_ in _COLUMNS:
        op.add_column("exercises", sa.Column(name, type_, nullable=True))
    op.create_check_constraint(
        op.f("ck_exercises_progression_settings"),
        "exercises",
        "(rep_min IS NULL OR rep_min >= 1) AND (rep_max IS NULL OR rep_max >= 1) "
        "AND (weight_step IS NULL OR weight_step > 0) AND (sets_max IS NULL OR sets_max >= 1)",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_exercises_progression_settings"), "exercises", type_="check")
    for name, _ in reversed(_COLUMNS):
        op.drop_column("exercises", name)
