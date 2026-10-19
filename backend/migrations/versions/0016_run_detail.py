"""run detail: elevation, cadence, elapsed time; stream key tracking for the refetch

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-19 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# STREAM_KEYS before 0016: rows fetched with these are refetched with altitude, cadence and latlng
OLD_STREAM_KEYS = "time,distance,heartrate,velocity_smooth,moving,grade_smooth"


def upgrade() -> None:
    op.add_column("activities", sa.Column("elapsed_seconds", sa.Integer(), nullable=True))
    op.add_column("activities", sa.Column("elevation_gain_m", sa.Float(), nullable=True))
    op.add_column("activities", sa.Column("avg_cadence", sa.Float(), nullable=True))
    op.add_column("activity_streams", sa.Column("keys", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.execute(sa.text("UPDATE activity_streams SET keys = :keys").bindparams(keys=OLD_STREAM_KEYS))


def downgrade() -> None:
    op.drop_column("activity_streams", "keys")
    op.drop_column("activities", "avg_cadence")
    op.drop_column("activities", "elevation_gain_m")
    op.drop_column("activities", "elapsed_seconds")
