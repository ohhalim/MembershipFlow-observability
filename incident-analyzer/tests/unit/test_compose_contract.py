from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def test_incident_worker_receives_webhook_secret() -> None:
    compose = (PROJECT_ROOT / "docker-compose.yml").read_text()
    worker = compose.split("  incident-worker:", maxsplit=1)[1].split(
        "  loki:", maxsplit=1
    )[0]

    assert "INCIDENT_WEBHOOK_SECRET: ${INCIDENT_WEBHOOK_SECRET}" in worker
