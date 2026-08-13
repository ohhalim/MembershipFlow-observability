from datetime import UTC, datetime

import pytest

from app.operations.synthetic_incident import build_payload, sign
from app.security.webhook import GrafanaWebhook, verify_webhook_signature


def test_synthetic_payment_incident_matches_webhook_contract() -> None:
    started_at = datetime(2026, 8, 13, 3, 0, tzinfo=UTC)
    body = build_payload("smoke-20260813", "production", started_at)
    payload = GrafanaWebhook.model_validate_json(body)

    assert payload.alerts[0].labels == {
        "alertname": "PaymentPrepareLoadTest-smoke-20260813",
        "service": "MembershipFlow",
        "environment": "production",
        "route": "/api/v1/subscriptions/prepare",
        "severity": "warning",
    }
    assert payload.alerts[0].starts_at == started_at

    signature = sign(body, "1786590000", "test-secret")
    verify_webhook_signature(
        body,
        "1786590000",
        signature,
        "test-secret",
        300,
        now=1786590000,
    )


@pytest.mark.parametrize("run_id", ["", "a", "contains space", "slash/test"])
def test_synthetic_payment_incident_rejects_unsafe_run_id(run_id: str) -> None:
    with pytest.raises(ValueError, match="run-id"):
        build_payload(run_id, "local", datetime.now(UTC))
