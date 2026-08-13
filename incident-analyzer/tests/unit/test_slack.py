from datetime import UTC, datetime

import httpx
import pytest

from app.domain.notification import ClaimedNotificationDelivery
from app.notifications import (
    SlackDeliveryError,
    SlackIncomingWebhookClient,
    render_incident_message,
)


def delivery() -> ClaimedNotificationDelivery:
    return ClaimedNotificationDelivery(
        delivery_id=1,
        incident_id="01TESTINCIDENT0000000000000",
        analysis_revision=1,
        started_at=datetime(2026, 8, 10, 2, 0, tzinfo=UTC),
        masked_event={
            "labels": {"alertname": "ApplicationErrorBurst"},
            "route": "/api/v1/courses",
        },
        analysis={
            "status": "ANALYZED",
            "facts": [{"statement": "동일 예외 23건 확인", "evidenceIds": ["L1"]}],
            "hypotheses": [
                {
                    "cause": "외부 응답 지연 후보",
                    "confidence": "MEDIUM",
                    "evidenceIds": ["L1"],
                }
            ],
            "excludedCandidates": [],
            "missingEvidence": [],
            "nextChecks": ["거래소별 응답 시간 확인"],
            "rootCauseConfirmed": False,
        },
    )


def test_render_incident_message_contains_bounded_analysis() -> None:
    payload = render_incident_message(delivery())
    rendered = str(payload)

    assert payload["text"] == (
        "MembershipFlow 장애 분석: ApplicationErrorBurst (ANALYZED)"
    )
    assert "동일 예외 23건 확인" in rendered
    assert "외부 응답 지연 후보" in rendered
    assert "원인 확정 아님" in rendered
    assert "masked sample" not in rendered


@pytest.mark.anyio
async def test_slack_client_accepts_ok_response() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        return httpx.Response(200, text="ok")

    client = SlackIncomingWebhookClient(
        "https://hooks.slack.com/services/test/test/test",
        1,
        httpx.MockTransport(handler),
    )

    await client.send({"text": "test"})


@pytest.mark.anyio
async def test_slack_client_preserves_retry_after() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "17"})

    client = SlackIncomingWebhookClient(
        "https://hooks.slack.com/services/test/test/test",
        1,
        httpx.MockTransport(handler),
    )

    with pytest.raises(SlackDeliveryError) as error:
        await client.send({"text": "test"})

    assert error.value.code == "SLACK_RATE_LIMITED"
    assert error.value.retryable is True
    assert error.value.retry_after_seconds == 17


@pytest.mark.anyio
async def test_slack_client_rejects_permanent_error() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="invalid_token")

    client = SlackIncomingWebhookClient(
        "https://hooks.slack.com/services/test/test/test",
        1,
        httpx.MockTransport(handler),
    )

    with pytest.raises(SlackDeliveryError) as error:
        await client.send({"text": "test"})

    assert error.value.code == "SLACK_REJECTED"
    assert error.value.retryable is False
