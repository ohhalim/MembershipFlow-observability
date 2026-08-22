from app.collectors.alert import build_alert_evidence


def test_build_alert_evidence_uses_only_sanitized_event_fields() -> None:
    evidence = build_alert_evidence(
        {
            "status": "firing",
            "labels": {
                "alertname": "DatabaseConnectionPoolPending",
                "service": "MembershipFlow",
                "environment": "production",
                "route": "database-connection-pool",
                "severity": "critical",
            },
            "values": {"A": 3.0, "C": 1.0},
        }
    )

    assert len(evidence) == 1
    assert evidence[0].evidence_id == "A1"
    assert evidence[0].route == "database-connection-pool"
    assert evidence[0].values == {"A": 3.0, "C": 1.0}


def test_build_alert_evidence_rejects_event_without_allowlisted_labels() -> None:
    assert build_alert_evidence({"status": "firing", "values": {"A": 1.0}}) == []
