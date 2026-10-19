"""foods.hidden (E28): kept as a micros reference, left out of the food list and Czech search

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-18 22:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("foods", sa.Column("hidden", sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade() -> None:
    op.drop_column("foods", "hidden")
