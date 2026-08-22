import hashlib
import hmac
import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

import app.api.incidents as incidents_api
import app.main as main_module
from app.domain.incident import CreatedIncident
from app.persistence.database import get_session
from app.security.webhook import (
    GrafanaWebhook,
    to_create_commands,
    verify_webhook_signature,
)

SECRET = "test_webhook_secret_at_least_32_characters"


def sign(body: bytes, timestamp: str) -> str:
    return hmac.new(
        SECRET.encode(), timestamp.encode() + b":" + body, hashlib.sha256
    ).hexdigest()


@pytest.mark.parametrize(
    ("timestamp", "now"),
    [("1700000000", 1700000000), ("1700000000000", 1700000000)],
)
def test_signature_accepts_current_untampered_body(timestamp: str, now: int) -> None:
    body = b'{"status":"firing"}'

    verify_webhook_signature(
        body, timestamp, sign(body, timestamp), SECRET, 300, now=now
    )


@pytest.mark.parametrize("timestamp", ["", "17000000000", "not-a-timestamp"])
def test_signature_rejects_invalid_timestamp_format(timestamp: str) -> None:
    body = b'{"status":"firing"}'

    with pytest.raises(ValueError, match="invalid webhook timestamp"):
        verify_webhook_signature(
            body, timestamp, sign(body, timestamp), SECRET, 300, now=1700000000
        )


@pytest.mark.parametrize("tamper", ["body", "signature", "expired"])
def test_signature_rejects_tampering_or_expired_timestamp(tamper: str) -> None:
    body = b'{"status":"firing"}'
    timestamp = "1700000000"
    signature = sign(body, timestamp)
    now = 1700000000
    if tamper == "body":
        body = b'{"status":"resolved"}'
    elif tamper == "signature":
        signature = "0" * 64
    else:
        now += 301

    with pytest.raises(ValueError):
        verify_webhook_signature(body, timestamp, signature, SECRET, 300, now=now)


def test_payload_keeps_only_allowlisted_labels() -> None:
    payload = GrafanaWebhook.model_validate(
        {
            "status": "firing",
            "alerts": [
                {
                    "status": "firing",
                    "labels": {
                        "alertname": "ApplicationErrorBurst",
                        "service": "membershipflow-backend",
                        "environment": "local",
                        "route": "/api/v1/courses",
                        "severity": "warning",
                        "email": "member@example.com",
                        "token": "secret-token",
                    },
                    "startsAt": datetime.now(UTC).isoformat(),
                    "fingerprint": "fixture-1",
                    "values": {
                        "A": 0.91,
                        "C": 1,
                        "unsafe": "member@example.com",
                        "infinite": float("inf"),
                    },
                }
            ],
        }
    )

    command = to_create_commands(payload)[0]
    serialized = json.dumps(command.masked_event)

    assert "email" not in serialized
    assert "token" not in serialized
    assert command.masked_event["values"] == {"A": 0.91, "C": 1.0}
    assert (
        command.dedup_key
        == hashlib.sha256(
            b"local|membershipflow-backend|ApplicationErrorBurst|/api/v1/courses|warning"
        ).hexdigest()
    )


def test_incident_endpoint_accepts_signed_payload(monkeypatch) -> None:
    now = int(datetime.now(UTC).timestamp())
    body = json.dumps(
        {
            "status": "firing",
            "alerts": [
                {
                    "status": "firing",
                    "labels": {"alertname": "ApplicationErrorBurst"},
                    "startsAt": datetime.now(UTC).isoformat(),
                }
            ],
        },
        separators=(",", ":"),
    ).encode()

    class FakeRepository:
        def create_many_with_jobs(self, _session, commands):
            assert len(commands) == 1
            return [CreatedIncident("01TESTINCIDENT000000000000", 1, 1)]

    application = main_module.create_app()
    application.dependency_overrides[get_session] = lambda: object()
    monkeypatch.setattr(incidents_api, "IncidentRepository", FakeRepository)
    monkeypatch.setattr(
        incidents_api,
        "get_settings",
        lambda: type(
            "TestSettings",
            (),
            {
                "incident_payload_max_bytes": 65_536,
                "incident_webhook_secret": type(
                    "Secret", (), {"get_secret_value": lambda self: SECRET}
                )(),
                "incident_webhook_tolerance_seconds": 300,
            },
        )(),
    )

    response = TestClient(application).post(
        "/internal/incidents",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Grafana-Alerting-Timestamp": str(now),
            "X-Grafana-Alerting-Signature": sign(body, str(now)),
        },
    )

    assert response.status_code == 202
    assert response.json()["accepted"] == 1
    assert response.json()["duplicates"] == 0


def test_incident_endpoint_reports_duplicate_payload(monkeypatch) -> None:
    now = int(datetime.now(UTC).timestamp())
    body = json.dumps(
        {
            "status": "firing",
            "alerts": [
                {
                    "status": "firing",
                    "labels": {"alertname": "ApplicationErrorBurst"},
                    "startsAt": datetime.now(UTC).isoformat(),
                }
            ],
        },
        separators=(",", ":"),
    ).encode()

    class FakeRepository:
        def create_many_with_jobs(self, _session, _commands):
            return []

    application = main_module.create_app()
    application.dependency_overrides[get_session] = lambda: object()
    monkeypatch.setattr(incidents_api, "IncidentRepository", FakeRepository)
    monkeypatch.setattr(
        incidents_api,
        "get_settings",
        lambda: type(
            "TestSettings",
            (),
            {
                "incident_payload_max_bytes": 65_536,
                "incident_webhook_secret": type(
                    "Secret", (), {"get_secret_value": lambda self: SECRET}
                )(),
                "incident_webhook_tolerance_seconds": 300,
            },
        )(),
    )

    response = TestClient(application).post(
        "/internal/incidents",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Grafana-Alerting-Timestamp": str(now),
            "X-Grafana-Alerting-Signature": sign(body, str(now)),
        },
    )

    assert response.status_code == 202
    assert response.json()["accepted"] == 0
    assert response.json()["duplicates"] == 1
    assert response.json()["incidentIds"] == []
