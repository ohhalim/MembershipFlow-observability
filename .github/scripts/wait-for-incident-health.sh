#!/usr/bin/env bash
set -euo pipefail

health_timeout_seconds="${INCIDENT_HEALTH_TIMEOUT_SECONDS:-120}"
health_retry_seconds="${INCIDENT_HEALTH_RETRY_SECONDS:-2}"
compose=(docker compose)

print_diagnostics() {
  "${compose[@]}" ps incident-api incident-worker loki prometheus grafana || true
  "${compose[@]}" logs --tail=100 incident-api incident-worker loki prometheus grafana || true
}

if ! "${compose[@]}" up -d --no-deps --wait \
  --wait-timeout "${health_timeout_seconds}" incident-api incident-worker; then
  echo "ERROR: incident API or worker did not start within ${health_timeout_seconds}s"
  print_diagnostics
  exit 1
fi

for service in incident-api incident-worker loki prometheus grafana; do
  container_id="$("${compose[@]}" ps -q "${service}")"
  if [[ -z "${container_id}" ]]; then
    echo "ERROR: ${service} container was not created"
    print_diagnostics
    exit 1
  fi

  state="$(docker inspect --format '{{.State.Status}} {{.State.Restarting}}' "${container_id}")"
  if [[ "${state}" != "running false" ]]; then
    echo "ERROR: ${service} state=${state}"
    print_diagnostics
    exit 1
  fi
done

"${compose[@]}" exec -T incident-api python -m app.healthcheck ready

loki_deadline=$((SECONDS + health_timeout_seconds))
until "${compose[@]}" exec -T incident-worker python -c \
  'import urllib.request; response = urllib.request.urlopen("http://loki:3100/ready", timeout=3); raise SystemExit(0 if response.status == 200 else 1)' \
  >/dev/null 2>&1; do
  if (( SECONDS >= loki_deadline )); then
    echo "ERROR: Loki did not become ready within ${health_timeout_seconds}s"
    print_diagnostics
    exit 1
  fi
  sleep "${health_retry_seconds}"
done

echo "Observability health gate passed"
