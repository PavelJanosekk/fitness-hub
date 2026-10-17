"""rename Dragon Fly to Dragon Flag

The exercise was named "Dragon Fly 🐉" in Strong by mistake; it is the dragon flag. Renaming in place keeps all
history and templates (they reference the exercise id). Skipped if a "Dragon Flag" row already exists.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-17 19:20:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE exercises SET name = 'Dragon Flag' WHERE name = 'Dragon Fly 🐉'"
            " AND NOT EXISTS (SELECT 1 FROM exercises WHERE name = 'Dragon Flag')"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("UPDATE exercises SET name = 'Dragon Fly 🐉' WHERE name = 'Dragon Flag'"))
