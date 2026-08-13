from datetime import UTC
from typing import Any

import httpx

from app.domain.notification import ClaimedNotificationDelivery


class SlackDeliveryError(Exception):
    def __init__(
        self,
        code: str,
        retryable: bool,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds


class SlackIncomingWebhookClient:
    def __init__(
        self,
        webhook_url: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not webhook_url.startswith("https://hooks.slack.com/services/"):
            raise ValueError("Slack webhook URL is invalid")
        self.webhook_url = webhook_url
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    async def send(self, payload: dict[str, Any]) -> None:
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds, transport=self.transport
            ) as client:
                response = await client.post(self.webhook_url, json=payload)
        except httpx.RequestError as exc:
            raise SlackDeliveryError("SLACK_UNAVAILABLE", True) from exc

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "1")
            try:
                retry_after_seconds = max(1, min(int(retry_after), 3600))
            except ValueError:
                retry_after_seconds = 1
            raise SlackDeliveryError("SLACK_RATE_LIMITED", True, retry_after_seconds)
        if response.status_code >= 500:
            raise SlackDeliveryError("SLACK_UNAVAILABLE", True)
        if response.status_code >= 400:
            raise SlackDeliveryError("SLACK_REJECTED", False)
        if response.text.strip() != "ok":
            raise SlackDeliveryError("SLACK_INVALID_RESPONSE", False)


def _event_value(event: dict[str, Any], key: str, fallback: str = "-") -> str:
    labels = event.get("labels")
    value = labels.get(key) if isinstance(labels, dict) else None
    if value is None:
        value = event.get(key)
    return str(value)[:200] if value not in (None, "") else fallback


def _bullet_lines(items: list[str], limit: int) -> str:
    selected = [f"• {item[:500]}" for item in items[:limit]]
    return "\n".join(selected) if selected else "• 없음"


def render_incident_message(
    delivery: ClaimedNotificationDelivery,
) -> dict[str, Any]:
    result = delivery.analysis
    facts = [
        f"{item.get('statement', '-')} [{', '.join(item.get('evidenceIds', []))}]"
        for item in result.get("facts", [])
    ]
    hypotheses = [
        (
            f"{item.get('cause', '-')} — {item.get('confidence', 'UNKNOWN')} "
            f"[{', '.join(item.get('evidenceIds', []))}]"
        )
        for item in result.get("hypotheses", [])
    ]
    excluded = [item.get("cause", "-") for item in result.get("excludedCandidates", [])]
    next_checks = [str(item) for item in result.get("nextChecks", [])]
    missing = [str(item) for item in result.get("missingEvidence", [])]
    alert_name = _event_value(delivery.masked_event, "alertname", "UnknownAlert")
    route = _event_value(delivery.masked_event, "route")
    status = str(result.get("status", "UNKNOWN"))
    started_at = delivery.started_at.astimezone(UTC).isoformat()

    text = f"MembershipFlow 장애 분석: {alert_name} ({status})"
    return {
        "text": text,
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "🚨 MembershipFlow 장애 분석"},
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*알림*\n{alert_name}"},
                    {"type": "mrkdwn", "text": f"*분석 상태*\n{status}"},
                    {"type": "mrkdwn", "text": f"*경로*\n{route}"},
                    {"type": "mrkdwn", "text": f"*발생 시각*\n{started_at}"},
                ],
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*확인된 사실*\n{_bullet_lines(facts, 5)}",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*원인 후보*\n{_bullet_lines(hypotheses, 3)}",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*제외된 후보*\n{_bullet_lines(excluded, 3)}",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*부족한 근거*\n{_bullet_lines(missing, 5)}",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*다음 확인*\n{_bullet_lines(next_checks, 5)}",
                },
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": (
                            "원인 확정 아님 · "
                            f"Incident `{delivery.incident_id}` · revision {delivery.analysis_revision}"
                        ),
                    }
                ],
            },
        ],
    }
