#!/usr/bin/env bash
# Shared, transaction-safe migration runner. Source this file from the RDS
# scripts or the local Postgres init hook; do not execute it directly.

run_migrations() {
  local conn="$1"
  local app_db_user="$2"
  local migrations_dir="${3:-migrations}"
  local file version checksum recorded

  if [[ ! "$app_db_user" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
    echo "APP_DB_USER must be a simple PostgreSQL role name." >&2
    return 2
  fi

  psql "$conn" -v ON_ERROR_STOP=1 <<SQL
CREATE TABLE IF NOT EXISTS schema_migrations (
  version text PRIMARY KEY,
  checksum text NOT NULL,
  applied_at timestamptz NOT NULL DEFAULT now()
);
SQL

  for file in "$migrations_dir"/[0-9][0-9][0-9][0-9]_*.sql; do
    [[ -e "$file" ]] || continue
    version="$(basename "$file" .sql)"
    checksum="$(shasum -a 256 "$file" | awk '{print $1}')"
    recorded="$(psql "$conn" -v ON_ERROR_STOP=1 -Atqc \
      "SELECT checksum FROM schema_migrations WHERE version = '$version'")"

    if [[ -n "$recorded" ]]; then
      if [[ "$recorded" != "$checksum" ]]; then
        echo "Migration checksum mismatch for $version. Do not edit an applied migration." >&2
        return 1
      fi
      echo "-> $version already applied"
      continue
    fi

    echo "-> applying $version"
    # The migration DDL and its history row commit atomically. If a statement
    # fails, ON_ERROR_STOP causes a rollback and the version is not recorded.
    psql "$conn" -v ON_ERROR_STOP=1 \
      -c 'BEGIN' \
      -f "$file" \
      -c "INSERT INTO schema_migrations (version, checksum) VALUES ('$version', '$checksum')" \
      -c 'COMMIT'
  done

  # Migrations create tables after the initial app role setup. Regranting is
  # intentional and idempotent; migration history itself remains private.
  psql "$conn" -v ON_ERROR_STOP=1 <<SQL
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ${app_db_user};
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ${app_db_user};
REVOKE ALL ON TABLE schema_migrations FROM ${app_db_user};
SQL
}
