from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.persistence.database import get_session
from app.persistence.repositories import IncidentRepository
from app.security.webhook import (
    GrafanaWebhook,
    to_create_commands,
    verify_webhook_signature,
)

router = APIRouter(prefix="/internal")


@router.post("/incidents", status_code=status.HTTP_202_ACCEPTED)
async def create_incidents(
    request: Request,
    signature: Annotated[str, Header(alias="X-Grafana-Alerting-Signature")],
    sent_at: Annotated[str, Header(alias="X-Grafana-Alerting-Timestamp")],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, object]:
    settings = get_settings()
    raw_body = await request.body()
    if len(raw_body) > settings.incident_payload_max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="incident payload too large",
        )
    try:
        verify_webhook_signature(
            raw_body,
            sent_at,
            signature,
            settings.incident_webhook_secret.get_secret_value(),
            settings.incident_webhook_tolerance_seconds,
        )
        payload = GrafanaWebhook.model_validate_json(raw_body)
    except (ValueError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid incident webhook",
        ) from None

    created = IncidentRepository().create_many_with_jobs(
        session, to_create_commands(payload)
    )
    return {
        "accepted": len(created),
        "duplicates": len(payload.alerts) - len(created),
        "incidentIds": [item.incident_id for item in created],
    }
