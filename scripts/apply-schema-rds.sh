#!/usr/bin/env bash
# apply-schema-rds.sh — set up the placement schema, RLS, and roles on ANY
# Postgres host (an RDS instance included). Run this from your laptop, over
# an SSH tunnel to a private RDS instance (see STARTUP_GUIDE.md), or directly
# if the instance is temporarily public.
#
# Usage:
#   ./scripts/apply-schema-rds.sh          # schema + roles only
#   ./scripts/apply-schema-rds.sh seed     # ...plus demo data
#
# Reads target host/db/role NAMES from .env. The RDS master PASSWORD is never
# stored on disk — it's prompted for interactively, used for this run only.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo "No .env found — copy .env.example to .env and fill it in first." >&2
  exit 1
fi
set -a; source .env; set +a

: "${RDS_HOST:?set RDS_HOST in .env — the RDS endpoint}"
RDS_PORT="${RDS_PORT:-5432}"
RDS_DB="${RDS_DB:-placement}"
: "${RDS_ADMIN_USER:?set RDS_ADMIN_USER in .env — the RDS master username}"
: "${APP_DB_USER:?set APP_DB_USER in .env}"
: "${APP_DB_PASSWORD:?set APP_DB_PASSWORD in .env}"
: "${MONITOR_DB_USER:?set MONITOR_DB_USER in .env}"
: "${MONITOR_DB_PASSWORD:?set MONITOR_DB_PASSWORD in .env}"

SEED="${1:-}"
CONN="host=${RDS_HOST} port=${RDS_PORT} dbname=${RDS_DB} user=${RDS_ADMIN_USER} sslmode=prefer"

echo "Target: ${RDS_HOST}:${RDS_PORT}/${RDS_DB}  (admin user: ${RDS_ADMIN_USER})"
read -r -s -p "RDS master password: " PGPASSWORD
echo
export PGPASSWORD

echo "-> applying schema + RLS policies (01-schema.sql) ..."
psql "$CONN" -v ON_ERROR_STOP=1 -f backend/db-init/01-schema.sql

echo "-> creating app_user + monitor roles (idempotent) ..."
psql "$CONN" -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${APP_DB_USER}') THEN
    CREATE ROLE ${APP_DB_USER} LOGIN PASSWORD '${APP_DB_PASSWORD}';
  END IF;
END \$\$;
GRANT USAGE ON SCHEMA public TO ${APP_DB_USER};
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ${APP_DB_USER};
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ${APP_DB_USER};
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ${APP_DB_USER};
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO ${APP_DB_USER};

-- monitor: read-only, stats-only role for the Prometheus postgres-exporter.
-- pg_monitor is a built-in Postgres role that exposes monitoring views
-- WITHOUT granting access to actual table data — the exporter never needs
-- to read a student's row to report connection counts and cache hit ratio.
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${MONITOR_DB_USER}') THEN
    CREATE ROLE ${MONITOR_DB_USER} LOGIN PASSWORD '${MONITOR_DB_PASSWORD}';
  END IF;
END \$\$;
GRANT pg_monitor TO ${MONITOR_DB_USER};
SQL

if [ "$SEED" = "seed" ]; then
  echo "-> loading demo seed data (03-seed.sql) ..."
  psql "$CONN" -v ON_ERROR_STOP=1 -f backend/db-init/03-seed.sql
fi

unset PGPASSWORD
echo "Done. app_user='${APP_DB_USER}' and monitor_user='${MONITOR_DB_USER}' are ready on '${RDS_DB}'."
