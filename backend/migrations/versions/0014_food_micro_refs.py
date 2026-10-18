"""food_micro_refs (E26): several micronutrient references per food, replacing foods.micros_reference_*

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-18 21:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "food_micro_refs",
        sa.Column("food_id", sa.Integer(), nullable=False),
        sa.Column("ref_food_id", sa.Integer(), nullable=False),
        sa.Column("grams_per_g", sa.Float(), nullable=False),
        sa.CheckConstraint("grams_per_g > 0 AND grams_per_g <= 5", name=op.f("ck_food_micro_refs_grams_per_g_range")),
        sa.CheckConstraint("food_id <> ref_food_id", name=op.f("ck_food_micro_refs_not_self")),
        sa.ForeignKeyConstraint(
            ["food_id"], ["foods.id"], name=op.f("fk_food_micro_refs_food_id_foods"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["ref_food_id"], ["foods.id"], name=op.f("fk_food_micro_refs_ref_food_id_foods"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("food_id", "ref_food_id", name=op.f("pk_food_micro_refs")),
    )
    op.create_index(op.f("ix_food_micro_refs_ref_food_id"), "food_micro_refs", ["ref_food_id"], unique=False)
    op.add_column("foods", sa.Column("micros_status", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.create_check_constraint(
        op.f("ck_foods_micros_status"),
        "foods",
        "micros_status IS NULL OR micros_status IN ('mapped', 'unmatched', 'manual')",
    )
    # The single C10 reference becomes one row
    op.execute(
        "INSERT INTO food_micro_refs (food_id, ref_food_id, grams_per_g) "
        "SELECT id, micros_reference_food_id, micros_reference_ratio FROM foods "
        "WHERE micros_reference_food_id IS NOT NULL AND micros_reference_ratio > 0 AND micros_reference_ratio <= 5"
    )
    op.execute("UPDATE foods SET micros_status = 'manual' WHERE id IN (SELECT food_id FROM food_micro_refs)")
    op.drop_constraint(op.f("fk_foods_micros_reference_food_id_foods"), "foods", type_="foreignkey")
    op.drop_column("foods", "micros_reference_ratio")
    op.drop_column("foods", "micros_reference_food_id")


def downgrade() -> None:
    op.add_column("foods", sa.Column("micros_reference_food_id", sa.Integer(), nullable=True))
    op.add_column("foods", sa.Column("micros_reference_ratio", sa.Float(), nullable=True))
    op.create_foreign_key(
        op.f("fk_foods_micros_reference_food_id_foods"),
        "foods",
        "foods",
        ["micros_reference_food_id"],
        ["id"],
        ondelete="SET NULL",
    )
    # Keeps the largest reference per food; the rest can't be represented
    op.execute(
        "UPDATE foods f SET micros_reference_food_id = r.ref_food_id, micros_reference_ratio = r.grams_per_g "
        "FROM (SELECT DISTINCT ON (food_id) food_id, ref_food_id, grams_per_g FROM food_micro_refs "
        "ORDER BY food_id, grams_per_g DESC) r WHERE f.id = r.food_id"
    )
    op.drop_constraint(op.f("ck_foods_micros_status"), "foods", type_="check")
    op.drop_column("foods", "micros_status")
    op.drop_index(op.f("ix_food_micro_refs_ref_food_id"), table_name="food_micro_refs")
    op.drop_table("food_micro_refs")
