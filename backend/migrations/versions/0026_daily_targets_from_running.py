"""Daily kcal target from running (E41): the profile keeps a base, protein and fat; meal type "fueling"

kcal_target becomes the base of a computed daily target, so kcal_target_training_day goes away, and carbs are
the remainder, so carbs_target_g goes away too. New: the maintenance offset and the Monday whose base proposal
was handled. Meals eaten during a run get their own type.

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-21 08:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MEALS = "'breakfast', 'morning_snack', 'lunch', 'afternoon_snack', 'dinner', 'second_dinner', {fueling}'other'"


def _meal_types(values: str) -> None:
    op.drop_constraint(op.f("ck_meal_logs_meal_type"), "meal_logs", type_="check")
    op.create_check_constraint(
        op.f("ck_meal_logs_meal_type"), "meal_logs", f"meal_type IS NULL OR meal_type IN ({values})"
    )


def upgrade() -> None:
    op.add_column("nutrition_profile", sa.Column("maintenance_offset_kcal", sa.Float(), nullable=True))
    op.add_column("nutrition_profile", sa.Column("base_proposal_handled_on", sa.Date(), nullable=True))
    op.drop_column("nutrition_profile", "kcal_target_training_day")
    op.drop_column("nutrition_profile", "carbs_target_g")
    _meal_types(_MEALS.format(fueling="'fueling', "))


def downgrade() -> None:
    op.execute("UPDATE meal_logs SET meal_type = 'other' WHERE meal_type = 'fueling'")
    _meal_types(_MEALS.format(fueling=""))
    op.add_column("nutrition_profile", sa.Column("carbs_target_g", sa.Float(), nullable=True))
    op.add_column("nutrition_profile", sa.Column("kcal_target_training_day", sa.Float(), nullable=True))
    op.drop_column("nutrition_profile", "base_proposal_handled_on")
    op.drop_column("nutrition_profile", "maintenance_offset_kcal")
