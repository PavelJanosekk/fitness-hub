import secrets
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, status

from app.config import settings
from app.database import SessionDep
from app.schemas.health import DayMerge, HealthPush
from app.services.health_ingest import ingest

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


def require_token(token: str | None) -> None:
    if not settings.webhook_token:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Webhooks disabled: set WEBHOOK_TOKEN")
    if token is None or not secrets.compare_digest(token, settings.webhook_token):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid webhook token")


@router.post("/health", response_model=list[DayMerge])
def health_push(
    push: HealthPush, session: SessionDep, x_webhook_token: Annotated[str | None, Header()] = None
) -> list[DayMerge]:
    """Steps/sleep from the iOS Shortcut (apple_health) or the Health Connect forwarder (samsung_health)."""
    require_token(x_webhook_token)
    return ingest(session, push)
