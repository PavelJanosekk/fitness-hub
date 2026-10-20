"""habit journal

Habit log modes, entries (note, stars, dovednost) on habit_logs and the abilities table (E37,
docs/habit-journal-module-spec.md). The two "new thing" habits from the 0012 seed switch to the note mode.

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-20 15:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NOTE_HABITS = ("Vyzkoušet jednu novou věc", "Učit se novou dovednost")


def upgrade() -> None:
    op.create_table(
        "abilities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("key", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("icon", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_abilities")),
        sa.UniqueConstraint("key", name=op.f("uq_abilities_key")),
    )
    op.add_column("habits", sa.Column("log_mode", sa.String(), nullable=False, server_default="check"))
    op.alter_column("habits", "log_mode", server_default=None)
    op.create_check_constraint(
        op.f("ck_habits_log_mode"), "habits", "log_mode IS NULL OR log_mode IN ('check', 'note', 'review')"
    )
    op.add_column("habit_logs", sa.Column("note", sa.String(), nullable=True))
    op.add_column("habit_logs", sa.Column("rating", sa.Integer(), nullable=True))
    op.add_column("habit_logs", sa.Column("ability_id", sa.Integer(), nullable=True))
    op.create_check_constraint(
        op.f("ck_habit_logs_rating_range"), "habit_logs", "rating IS NULL OR rating BETWEEN 1 AND 5"
    )
    op.create_foreign_key(
        op.f("fk_habit_logs_ability_id_abilities"),
        "habit_logs",
        "abilities",
        ["ability_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_habit_logs_ability_id"), "habit_logs", ["ability_id"], unique=False)
    habits = sa.table("habits", sa.column("title", sa.String()), sa.column("log_mode", sa.String()))
    op.execute(habits.update().where(habits.c.title.in_(NOTE_HABITS)).values(log_mode="note"))


def downgrade() -> None:
    op.drop_index(op.f("ix_habit_logs_ability_id"), table_name="habit_logs")
    op.drop_constraint(op.f("fk_habit_logs_ability_id_abilities"), "habit_logs", type_="foreignkey")
    op.drop_constraint(op.f("ck_habit_logs_rating_range"), "habit_logs", type_="check")
    op.drop_column("habit_logs", "ability_id")
    op.drop_column("habit_logs", "rating")
    op.drop_column("habit_logs", "note")
    op.drop_constraint(op.f("ck_habits_log_mode"), "habits", type_="check")
    op.drop_column("habits", "log_mode")
    op.drop_table("abilities")
