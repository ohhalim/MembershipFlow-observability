from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
PROVISIONING_ROOT = REPOSITORY_ROOT / "grafana" / "provisioning"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_incident_webhook_uses_grafana_hmac_contract() -> None:
    contact_point = read(PROVISIONING_ROOT / "alerting" / "incident-contactpoint.yaml")

    assert "http://incident-api:8000/internal/incidents" in contact_point
    assert "X-Grafana-Alerting-Signature" in contact_point
    assert "X-Grafana-Alerting-Timestamp" in contact_point
    assert "secret: ${INCIDENT_WEBHOOK_SECRET}" in contact_point
    assert "disableResolveMessage: true" in contact_point


def test_application_error_rule_matches_production_log_labels() -> None:
    data_source = read(PROVISIONING_ROOT / "datasources" / "prometheus.yml")
    rule = read(PROVISIONING_ROOT / "alerting" / "incident-rules.yaml")

    assert "uid: loki" in data_source
    assert "url: http://loki:3100" in data_source
    assert 'service="MembershipFlow"' in rule
    assert 'environment="production"' in rule
    assert 'level="ERROR"' in rule
    assert 'ai_analyze: "true"' in rule
    assert "interval: 1m" in rule


def test_prometheus_datasource_and_backend_down_rule_use_stable_uid() -> None:
    data_source = read(PROVISIONING_ROOT / "datasources" / "prometheus.yml")
    availability_rule = read(PROVISIONING_ROOT / "alerting" / "availability-rules.yaml")

    assert "uid: prometheus" in data_source
    assert "datasourceUid: prometheus" in availability_rule
    assert 'up{job="membershipflow-backend"}' in availability_rule
    assert "for: 1m" in availability_rule
    assert "route: application-health" in availability_rule


def test_batch_rules_use_process_start_as_restart_grace_period() -> None:
    rule = read(PROVISIONING_ROOT / "alerting" / "rules.yaml")

    assert "collect_last_run_timestamp_seconds|process_start_time_seconds" in rule
    assert "billing_last_run_timestamp_seconds|process_start_time_seconds" in rule
    assert "datasourceUid: prometheus" in rule


def test_incident_notification_policy_is_the_only_root_policy() -> None:
    policy_files = sorted((PROVISIONING_ROOT / "alerting").glob("*policy.y*ml"))

    assert [path.name for path in policy_files] == ["incident-notification-policy.yaml"]
    assert "receiver: incident-analyzer" in read(policy_files[0])


def test_cd_checks_only_alerting_provisioning_failures() -> None:
    workflow = read(REPOSITORY_ROOT / ".github" / "workflows" / "cd-pipeline.yml")

    assert "logger=provisioning.alerting.*level=error" in workflow
    assert "provisioning.*(error|failed)" not in workflow
