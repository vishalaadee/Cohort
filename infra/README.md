# Infrastructure

See [docs/INFRA.md](../docs/INFRA.md) for the full AWS setup guide,
zero-bill strategy, and peak-infra evolution.

## Files

- `docker-compose.yml` — local dev (includes a Postgres container)
- `docker-compose.aws.yml` — AWS deployment (database is RDS)
- `caddy/Caddyfile` — reverse proxy + auto-TLS + static file serving
- `monitoring/` — Prometheus scrape config + Grafana datasource provisioning
