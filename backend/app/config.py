from zoneinfo import ZoneInfo

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def normalize_database_url(url: str) -> str:
    """Force the psycopg 3 driver; .env may carry a plain postgresql:// URL."""
    for prefix in ("postgresql+psycopg2://", "postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url.removeprefix(prefix)
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    app_tz: str = "Europe/Prague"
    webhook_token: str | None = None  # required by /api/webhooks/*; webhooks are disabled while unset
    strava_client_id: str | None = None
    strava_client_secret: str | None = None
    # Public HTTPS origin (e.g. https://host.tailnet.ts.net) for OAuth redirects; falls back to the request URL
    public_base_url: str | None = None
    scheduler_enabled: bool = True

    @field_validator("database_url")
    @classmethod
    def _normalize_database_url(cls, value: str) -> str:
        return normalize_database_url(value)

    @field_validator("app_tz")
    @classmethod
    def _validate_app_tz(cls, value: str) -> str:
        ZoneInfo(value)  # fail fast on a typo instead of at the first date computation
        return value

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.app_tz)


settings = Settings()
