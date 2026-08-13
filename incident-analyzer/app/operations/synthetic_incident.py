import argparse
import hashlib
import hmac
import json
import re
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime

from app.config import get_settings

DEFAULT_API_URL = "http://127.0.0.1:8000/internal/incidents"
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")


def build_payload(run_id: str, environment: str, started_at: datetime) -> bytes:
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError("run-id must be 3-64 safe characters")
    payload = {
        "status": "firing",
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": f"PaymentPrepareLoadTest-{run_id}",
                    "service": "MembershipFlow",
                    "environment": environment,
                    "route": "/api/v1/subscriptions/prepare",
                    "severity": "warning",
                },
                "startsAt": started_at.astimezone(UTC).isoformat(),
                "fingerprint": f"payment-prepare-load-{run_id}",
            }
        ],
    }
    return json.dumps(payload, separators=(",", ":")).encode()


def sign(body: bytes, timestamp: str, secret: str) -> str:
    signed = timestamp.encode() + b":" + body
    return hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()


def send(api_url: str, body: bytes, timestamp: str, signature: str) -> dict:
    request = urllib.request.Request(
        api_url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Grafana-Alerting-Timestamp": timestamp,
            "X-Grafana-Alerting-Signature": signature,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            if response.status != 202:
                raise RuntimeError(f"incident API returned HTTP {response.status}")
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"incident API returned HTTP {error.code}") from error


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Send one signed synthetic incident through Gemini and Slack."
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Required acknowledgement that one Gemini analysis and Slack message will be created.",
    )
    args = parser.parse_args()
    if not args.confirm:
        parser.error("--confirm is required")

    settings = get_settings()
    now = datetime.now(UTC)
    timestamp = str(int(time.time()))
    body = build_payload(args.run_id, settings.app_environment, now)
    signature = sign(
        body,
        timestamp,
        settings.incident_webhook_secret.get_secret_value(),
    )
    result = send(args.api_url, body, timestamp, signature)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
