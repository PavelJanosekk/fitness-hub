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
