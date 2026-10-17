import datetime as dt

from sqlmodel import Field, SQLModel

from app.models.common import AwareDateTime


class IntegrationToken(SQLModel, table=True):
    """OAuth tokens + sync cursor of an external integration (currently only Strava)."""

    __tablename__ = "integration_tokens"

    provider: str = Field(primary_key=True)
    access_token: str
    refresh_token: str
    expires_at: dt.datetime = Field(sa_type=AwareDateTime)
    athlete_id: str | None = None
    last_synced_at: dt.datetime | None = Field(default=None, sa_type=AwareDateTime)
    last_activity_start: dt.datetime | None = Field(default=None, sa_type=AwareDateTime)
