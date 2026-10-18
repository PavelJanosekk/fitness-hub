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
    # Life Dashboard Companion (Health Connect forwarder): optional HMAC secret instead of the token header,
    # and the apps whose records count (comma-separated package names; "*" accepts every app)
    health_connect_secret: str | None = None
    health_connect_origins: str = "com.sec.android.app.shealth"
    # Gemini (docs/SPEC.md §3): model ids only from env; "smart" falls back to the fast model when unset.
    # Thinking level per tier: minimal | low | medium | high (empty = model default)
    gemini_api_key: str | None = None
    gemini_model_fast: str | None = None
    gemini_model_smart: str | None = None
    # Free-tier quotas are per model (E15): the nutrition assistant and the one-shot helpers (food picker, web
    # estimate) can each use their own model. Both fall back to gemini_model_fast.
    gemini_model_nutrition: str | None = None
    gemini_model_lite: str | None = None
    # Comma-separated models tried in order when an assistant's model is out of quota (429) or overloaded (503)
    gemini_model_fallbacks: str | None = None

    # KalorickéTabulky history import (Phase 5.5): credentials only ever live in .env
    kaloricketabulky_email: str | None = None
    kaloricketabulky_password: str | None = None
    gemini_thinking_fast: str | None = "low"
    gemini_thinking_smart: str | None = "high"
    # The user's running knowledge base on GitHub ("owner/repo"); read-only source for the coach (E11)
    coach_kb_repo: str | None = None
    coach_kb_branch: str = "master"
    # Built frontend (the prod image sets /app/static); unset in dev, where Vite serves the UI
    static_dir: str | None = None

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
