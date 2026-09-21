#!/usr/bin/env bash
# Fresh local databases must receive the same incremental migrations as RDS.
# The files are mounted read-only by docker-compose.yml.
set -euo pipefail
source /scripts/migration-lib.sh
run_migrations "dbname=${POSTGRES_DB} user=${POSTGRES_USER}" "$APP_DB_USER" "/migrations"
