from typing import Any

from app.domain.evidence import AlertEvidence


def build_alert_evidence(masked_event: dict[str, Any]) -> list[AlertEvidence]:
    labels = masked_event.get("labels")
    if not isinstance(labels, dict):
        return []

    values = masked_event.get("values")
    safe_values = values if isinstance(values, dict) else {}
    return [
        AlertEvidence(
            evidence_id="A1",
            alert_name=str(labels.get("alertname", "unknown")),
            service=str(labels.get("service", "unknown")),
            environment=str(labels.get("environment", "unknown")),
            route=str(labels.get("route", "unknown")),
            severity=str(labels.get("severity", "unknown")),
            values=safe_values,
        )
    ]
