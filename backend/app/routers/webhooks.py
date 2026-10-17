import hashlib
import hmac
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import ValidationError

from app.config import settings
from app.database import SessionDep
from app.schemas.health import DayMerge, HealthPush
from app.schemas.health_connect import HCPayload
from app.services.health_connect import HealthConnectResult, ingest_health_connect
from app.services.health_ingest import ingest

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


def require_token(token: str | None) -> None:
    if not settings.webhook_token:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Webhooks disabled: set WEBHOOK_TOKEN")
    if token is None or not secrets.compare_digest(token, settings.webhook_token):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid webhook token")


async def raw_body(request: Request) -> bytes:
    return await request.body()


@router.post("/health", response_model=list[DayMerge])
def health_push(
    push: HealthPush, session: SessionDep, x_webhook_token: Annotated[str | None, Header()] = None
) -> list[DayMerge]:
    """Complete-day pushes, e.g. from the iOS Shortcut (apple_health)."""
    require_token(x_webhook_token)
    return ingest(session, push)


@router.post("/health-connect", response_model=HealthConnectResult)
def health_connect_push(
    session: SessionDep,
    body: Annotated[bytes, Depends(raw_body)],
    x_webhook_token: Annotated[str | None, Header()] = None,
    x_signature: Annotated[str | None, Header()] = None,
) -> HealthConnectResult:
    """Incremental pushes from the Life Dashboard Companion app (Health Connect forwarder).

    Authenticated by its HMAC signature when HEALTH_CONNECT_SECRET is set, otherwise by X-Webhook-Token
    (configured as a custom header in the app). Responds quickly: the app gives up after 10 s.
    """
    secret = (settings.health_connect_secret or "").strip()
    if secret and x_signature:
        expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, x_signature):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid signature")
    else:
        require_token(x_webhook_token)
    try:
        payload = HCPayload.model_validate_json(body)
    except ValidationError as exc:
        # 422 makes the app keep this payload for a week while later ones still get through
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, exc.errors(include_url=False)) from None
    return ingest_health_connect(session, payload)
