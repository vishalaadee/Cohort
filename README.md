# Cohort

**One live view of every campus placement.** Cohort is a multi-tenant SaaS
platform that replaces a placement cell's spreadsheets and WhatsApp groups
with a single dashboard — roster-verified student onboarding, real-time
drive pipelines, and accreditation-ready exports.

---

## Quick start (local, ~3 minutes)

```bash
cp .env.example .env          # edit: set passwords + JWT_SECRET
cd infra
docker compose up -d --build  # starts backend, Postgres, Caddy, MinIO, monitoring
```

Open `http://localhost` → landing page. `http://localhost/app` → sign in with
`admin@demo.ac.in` / `demo1234` (seeded demo credentials).

For the **AWS + RDS** path, follow [docs/INFRA.md](docs/INFRA.md).

---

## Repo layout

```
Cohort/
├─ backend/              FastAPI app, tenant-scoped RLS, auth, CSV import
│  ├─ app/               application code
│  ├─ db-init/           schema + seed (auto-run on local, script for RDS)
│  └─ tests/             integration tests
├─ frontend/
│  ├─ public/            landing page (index.html)
│  └─ app/               product app: login, admin console, student portal
├─ infra/                Docker Compose (local + AWS), Caddy, Prometheus, Grafana
├─ scripts/              RDS setup, utilities
├─ migrations/           incremental schema changes (post-initial-setup)
├─ finance/              unit-economics tracker (.xlsx)
├─ docs/                 all guides
│  ├─ INFRA.md           AWS setup, zero-bill guide, peak-infra evolution
│  ├─ BACKEND.md         API architecture, RLS, auth flows, adding endpoints
│  ├─ FRONTEND.md        design system, app structure, adding views
│  └─ USAGE.md           Google SSO setup, college/student onboarding, per-role usage
└─ .env.example          template for all environment variables
```

Each `docs/*.md` is self-contained — start with whichever matches what you
need to do:

| I want to… | Read |
|---|---|
| Deploy on AWS for the first time | [docs/INFRA.md](docs/INFRA.md) |
| Understand the backend / add an API | [docs/BACKEND.md](docs/BACKEND.md) |
| Work on the UI / add a page | [docs/FRONTEND.md](docs/FRONTEND.md) |
| Onboard a college or set up Google SSO | [docs/USAGE.md](docs/USAGE.md) |

---

## Branch strategy

| Branch | Purpose | Merges into |
|---|---|---|
| `main` | stable, deployable at all times | — |
| `develop` | integration branch for ongoing work | `main` via PR |
| `feature/*` | one feature at a time (e.g. `feature/pipeline-write`) | `develop` via PR |
| `hotfix/*` | urgent prod fixes | `main` directly |

---

## Tech stack

**Backend:** FastAPI · SQLAlchemy 2 · PostgreSQL 16 with Row-Level Security ·
PyJWT · bcrypt · Google Auth (ID-token verify)

**Frontend:** vanilla HTML/CSS/JS (single-file app, same design system across
landing + product), migrating to React + TypeScript as features grow

**Infra:** Docker Compose · Caddy (TLS + reverse proxy) · Prometheus +
Grafana · MinIO (S3-compatible) · AWS RDS (managed Postgres)

**Design principles:** pooled multi-tenancy (one DB, `tenant_id` on every
row, RLS as the safety net), scope-based RBAC (owner → admin → sub_admin →
student/alumni), stateless API with JWT, containers that move unchanged from
laptop to EC2 to ECS.

---

## License

Private — not open source yet. All rights reserved.
