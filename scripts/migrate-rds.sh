#!/usr/bin/env bash
# Apply every tracked migration exactly once to an existing RDS database.
# This is the only supported path for schema changes after initial setup.
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -f .env ]]; then
  echo "No .env found — copy .env.example to .env and fill it in first." >&2
  exit 1
fi
set -a; source .env; set +a

: "${RDS_HOST:?set RDS_HOST in .env}"
RDS_PORT="${RDS_PORT:-5432}"
RDS_DB="${RDS_DB:-placement}"
: "${RDS_ADMIN_USER:?set RDS_ADMIN_USER in .env}"
: "${APP_DB_USER:?set APP_DB_USER in .env}"

CONN="host=${RDS_HOST} port=${RDS_PORT} dbname=${RDS_DB} user=${RDS_ADMIN_USER} sslmode=prefer"
echo "Target: ${RDS_HOST}:${RDS_PORT}/${RDS_DB} (admin user: ${RDS_ADMIN_USER})"
read -r -s -p "RDS master password: " PGPASSWORD
echo
export PGPASSWORD

source scripts/migration-lib.sh
run_migrations "$CONN" "$APP_DB_USER" "migrations"

unset PGPASSWORD
echo "Migrations are current."
