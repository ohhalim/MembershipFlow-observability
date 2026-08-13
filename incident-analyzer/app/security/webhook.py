import hashlib
import hmac
import time
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.incident import CreateIncidentCommand

ALLOWED_LABELS = {"alertname", "service", "environment", "route", "severity"}


class GrafanaAlert(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    status: Literal["firing"] = "firing"
    labels: dict[str, str]
    starts_at: datetime = Field(alias="startsAt")
    fingerprint: str | None = Field(default=None, max_length=255)

    @field_validator("starts_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("startsAt must include a timezone")
        return value


class GrafanaWebhook(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: Literal["firing"]
    alerts: list[GrafanaAlert] = Field(min_length=1, max_length=20)


def verify_webhook_signature(
    raw_body: bytes,
    timestamp: str,
    signature: str,
    secret: str,
    tolerance_seconds: int,
    now: int | None = None,
) -> None:
    if (
        not timestamp.isascii()
        or not timestamp.isdigit()
        or len(timestamp) not in {10, 13}
    ):
        raise ValueError("invalid webhook timestamp")

    try:
        sent_at_raw = int(timestamp)
    except ValueError as exc:
        raise ValueError("invalid webhook timestamp") from exc

    # Grafana versions can provide a Unix timestamp in seconds or milliseconds.
    # The original header value remains part of the HMAC input.
    sent_at = sent_at_raw // 1000 if len(timestamp) == 13 else sent_at_raw

    current = int(time.time()) if now is None else now
    if abs(current - sent_at) > tolerance_seconds:
        raise ValueError("expired webhook timestamp")

    # Grafana webhook HMAC contract: HMAC-SHA256(timestamp + ":" + raw body).
    # The timestamp header is included to reject replayed notifications.
    signed = timestamp.encode() + b":" + raw_body
    expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature.lower()):
        raise ValueError("invalid webhook signature")


def to_create_commands(payload: GrafanaWebhook) -> list[CreateIncidentCommand]:
    commands: list[CreateIncidentCommand] = []
    for alert in payload.alerts:
        labels = {
            key: value[:256]
            for key, value in alert.labels.items()
            if key in ALLOWED_LABELS
        }
        stable_parts = [
            labels.get("environment", "unknown"),
            labels.get("service", "unknown"),
            labels.get("alertname", "unknown"),
            labels.get("route", "unknown"),
            labels.get("severity", "unknown"),
        ]
        dedup_key = hashlib.sha256("|".join(stable_parts).encode()).hexdigest()
        commands.append(
            CreateIncidentCommand(
                dedup_key=dedup_key,
                started_at=alert.starts_at.astimezone(UTC),
                external_fingerprint=alert.fingerprint,
                masked_event={"status": alert.status, "labels": labels},
            )
        )
    return commands
