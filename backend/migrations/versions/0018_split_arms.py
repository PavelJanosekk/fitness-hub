"""exercises.muscle_group: "arms" is split into "biceps" and "triceps" (E32)

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-19 16:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BASE = "'chest', 'back', 'legs', 'shoulders', {arms}, 'core', 'full_body', 'cardio'"
# Name words of triceps movements (as the old radar heuristic); every other arm exercise is a curl
_TRICEPS = ("tricep", "pushdown", "skull", "kickback", "french", "close grip", "dip", "francouz")


def upgrade() -> None:
    op.drop_constraint(op.f("ck_exercises_muscle_group"), "exercises", type_="check")
    triceps = " OR ".join(f"lower(name) LIKE '%{word}%'" for word in _TRICEPS)
    op.execute(
        f"UPDATE exercises SET muscle_group = CASE WHEN {triceps} THEN 'triceps' ELSE 'biceps' END "
        "WHERE muscle_group = 'arms'"
    )
    op.create_check_constraint(
        op.f("ck_exercises_muscle_group"),
        "exercises",
        f"muscle_group IS NULL OR muscle_group IN ({_BASE.format(arms="'biceps', 'triceps'")})",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_exercises_muscle_group"), "exercises", type_="check")
    op.execute("UPDATE exercises SET muscle_group = 'arms' WHERE muscle_group IN ('biceps', 'triceps')")
    op.create_check_constraint(
        op.f("ck_exercises_muscle_group"),
        "exercises",
        f"muscle_group IS NULL OR muscle_group IN ({_BASE.format(arms="'arms'")})",
    )
