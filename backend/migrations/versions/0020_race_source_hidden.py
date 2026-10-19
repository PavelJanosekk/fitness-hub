"""races: source (kb | user) and hidden, so races can be added and removed in the app (E34)

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-19 20:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("races", sa.Column("source", sa.String(), server_default="kb", nullable=False))
    op.add_column("races", sa.Column("hidden", sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade() -> None:
    op.execute("DELETE FROM races WHERE source <> 'kb'")
    op.drop_column("races", "hidden")
    op.drop_column("races", "source")
