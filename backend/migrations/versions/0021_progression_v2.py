"""exercises: target RIR and strategy; workout_sets: the planned target, role and unusual flag (E35)

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-20 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("exercises", sa.Column("target_rir", sa.Integer(), nullable=True))
    op.add_column("exercises", sa.Column("strategy", sa.String(), nullable=True))
    op.create_check_constraint(
        op.f("ck_exercises_target_rir_range"), "exercises", "target_rir IS NULL OR target_rir BETWEEN 0 AND 3"
    )
    op.create_check_constraint(
        op.f("ck_exercises_strategy"), "exercises", "strategy IS NULL OR strategy IN ('straight', 'top_backoff')"
    )
    op.add_column("workout_sets", sa.Column("planned_weight_kg", sa.Float(), nullable=True))
    op.add_column("workout_sets", sa.Column("planned_reps", sa.Integer(), nullable=True))
    op.add_column("workout_sets", sa.Column("role", sa.String(), nullable=True))
    op.add_column("workout_sets", sa.Column("unusual", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.create_check_constraint(
        op.f("ck_workout_sets_role"), "workout_sets", "role IS NULL OR role IN ('straight', 'top', 'backoff')"
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_workout_sets_role"), "workout_sets", type_="check")
    for column in ("unusual", "role", "planned_reps", "planned_weight_kg"):
        op.drop_column("workout_sets", column)
    op.drop_constraint(op.f("ck_exercises_strategy"), "exercises", type_="check")
    op.drop_constraint(op.f("ck_exercises_target_rir_range"), "exercises", type_="check")
    op.drop_column("exercises", "strategy")
    op.drop_column("exercises", "target_rir")
