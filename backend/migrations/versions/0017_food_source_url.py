"""foods.source_url: the web recipe a looked-up dish was computed from (E30)

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-19 14:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("foods", sa.Column("source_url", sqlmodel.sql.sqltypes.AutoString(), nullable=True))


def downgrade() -> None:
    op.drop_column("foods", "source_url")
