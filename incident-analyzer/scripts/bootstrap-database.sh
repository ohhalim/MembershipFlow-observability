#!/bin/sh
set -eu

: "${MYSQL_ROOT_PASSWORD:?MYSQL_ROOT_PASSWORD is required}"
: "${INCIDENT_DB_RUNTIME_PASSWORD:?INCIDENT_DB_RUNTIME_PASSWORD is required}"
: "${INCIDENT_DB_MIGRATION_PASSWORD:?INCIDENT_DB_MIGRATION_PASSWORD is required}"

runtime_user="${INCIDENT_DB_RUNTIME_USERNAME:-incident_analyzer_runtime}"
migration_user="${INCIDENT_DB_MIGRATION_USERNAME:-incident_analyzer_migrator}"
database="${INCIDENT_DB_NAME:-membershipflow_incident}"
mysql_host="${MYSQL_HOST:-mysql}"

validate_identifier() {
    case "$1" in
        ""|*[!A-Za-z0-9_]*)
            echo "database and user identifiers must contain only letters, digits, and underscore" >&2
            exit 1
            ;;
    esac
}

validate_password() {
    if [ "${#1}" -lt 16 ]; then
        echo "incident database passwords must be at least 16 characters" >&2
        exit 1
    fi
    case "$1" in
        *[!A-Za-z0-9_-]*)
            echo "incident database passwords must use base64url characters" >&2
            exit 1
            ;;
    esac
}

validate_identifier "$runtime_user"
validate_identifier "$migration_user"
validate_identifier "$database"
validate_password "$INCIDENT_DB_RUNTIME_PASSWORD"
validate_password "$INCIDENT_DB_MIGRATION_PASSWORD"

export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"

attempt=0
until mysqladmin --protocol=tcp -h "$mysql_host" -u root ping --silent; do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge 30 ]; then
        echo "mysql did not become ready" >&2
        exit 1
    fi
    sleep 2
done

mysql --protocol=tcp -h "$mysql_host" -u root --batch --skip-column-names <<SQL
CREATE DATABASE IF NOT EXISTS \`${database}\`
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE USER IF NOT EXISTS '${runtime_user}'@'%' IDENTIFIED BY '${INCIDENT_DB_RUNTIME_PASSWORD}';
ALTER USER '${runtime_user}'@'%' IDENTIFIED BY '${INCIDENT_DB_RUNTIME_PASSWORD}';
REVOKE ALL PRIVILEGES, GRANT OPTION FROM '${runtime_user}'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE ON \`${database}\`.* TO '${runtime_user}'@'%';

CREATE USER IF NOT EXISTS '${migration_user}'@'%' IDENTIFIED BY '${INCIDENT_DB_MIGRATION_PASSWORD}';
ALTER USER '${migration_user}'@'%' IDENTIFIED BY '${INCIDENT_DB_MIGRATION_PASSWORD}';
REVOKE ALL PRIVILEGES, GRANT OPTION FROM '${migration_user}'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, REFERENCES
  ON \`${database}\`.* TO '${migration_user}'@'%';

FLUSH PRIVILEGES;
SQL

echo "incident database and isolated users are ready"
