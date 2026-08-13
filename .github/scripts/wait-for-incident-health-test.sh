#!/usr/bin/env bash
set -euo pipefail

script_directory="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fixture_directory="$(mktemp -d)"
trap 'rm -rf "${fixture_directory}"' EXIT

cat > "${fixture_directory}/docker" <<'FAKE_DOCKER'
#!/usr/bin/env bash
set -euo pipefail

arguments="$*"
case "${arguments}" in
  "compose up -d --no-deps --wait --wait-timeout "*" incident-api incident-worker")
    exit "${FAKE_UP_EXIT:-0}"
    ;;
  "compose ps -q "*)
    service="${arguments##* }"
    if [[ "${FAKE_MISSING_SERVICE:-}" == "${service}" ]]; then
      exit 0
    fi
    printf '%s-container\n' "${service}"
    ;;
  "inspect --format "*)
    printf '%s %s\n' "${FAKE_STATUS:-running}" "${FAKE_RESTARTING:-false}"
    ;;
  "compose exec -T incident-api python -m app.healthcheck ready")
    exit "${FAKE_API_READY_EXIT:-0}"
    ;;
  "compose exec -T incident-worker python -c "*)
    exit "${FAKE_LOKI_READY_EXIT:-0}"
    ;;
  "compose ps incident-api incident-worker loki prometheus grafana")
    printf '%s\n' "observability diagnostic status"
    ;;
  "compose logs --tail=100 incident-api incident-worker loki prometheus grafana")
    printf '%s\n' "observability diagnostic logs"
    ;;
  *)
    printf 'unexpected docker arguments: %s\n' "${arguments}" >&2
    exit 2
    ;;
esac
FAKE_DOCKER
chmod +x "${fixture_directory}/docker"

PATH="${fixture_directory}:${PATH}" \
  bash "${script_directory}/wait-for-incident-health.sh" >/dev/null

if failure_output="$(PATH="${fixture_directory}:${PATH}" FAKE_UP_EXIT=1 \
  bash "${script_directory}/wait-for-incident-health.sh" 2>&1)"; then
  echo "expected incident compose wait failure" >&2
  exit 1
fi
[[ "${failure_output}" == *"observability diagnostic status"* ]]
[[ "${failure_output}" == *"observability diagnostic logs"* ]]

if failure_output="$(PATH="${fixture_directory}:${PATH}" FAKE_MISSING_SERVICE=loki \
  bash "${script_directory}/wait-for-incident-health.sh" 2>&1)"; then
  echo "expected missing Loki container failure" >&2
  exit 1
fi
[[ "${failure_output}" == *"loki container was not created"* ]]

if failure_output="$(PATH="${fixture_directory}:${PATH}" \
  INCIDENT_HEALTH_TIMEOUT_SECONDS=0 INCIDENT_HEALTH_RETRY_SECONDS=0 \
  FAKE_LOKI_READY_EXIT=1 bash "${script_directory}/wait-for-incident-health.sh" 2>&1)"; then
  echo "expected Loki readiness timeout" >&2
  exit 1
fi
[[ "${failure_output}" == *"Loki did not become ready"* ]]
[[ "${failure_output}" == *"observability diagnostic logs"* ]]

echo "Observability health gate tests passed"

