"""daily_source_metrics.metric: "steps_untimed" for steps from records too long to place in time (E38)

Samsung Health writes one whole-day step record to Health Connect. Spread over 15-minute buckets it
inflated the per-bucket merge, so such steps now only count toward the source's daily total.

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-20 21:30:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BASE = "'steps_total', {untimed}'sleep_minutes', 'resting_hr', 'weight_kg'"


def _constraint(values: str) -> None:
    op.drop_constraint(op.f("ck_daily_source_metrics_metric"), "daily_source_metrics", type_="check")
    op.create_check_constraint(
        op.f("ck_daily_source_metrics_metric"), "daily_source_metrics", f"metric IS NULL OR metric IN ({values})"
    )


def upgrade() -> None:
    _constraint(_BASE.format(untimed="'steps_untimed', "))


def downgrade() -> None:
    op.execute("DELETE FROM daily_source_metrics WHERE metric = 'steps_untimed'")
    _constraint(_BASE.format(untimed=""))
