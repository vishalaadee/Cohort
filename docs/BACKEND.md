# Backend

FastAPI application serving the Cohort API. Every query is tenant-scoped by
PostgreSQL Row-Level Security — the same code serves every college, and each
caller only ever sees their own rows.

## Running locally

```bash
cd backend
pip install -r requirements.txt
# needs a Postgres with the schema applied (docker compose does this automatically)
DATABASE_URL="postgresql+psycopg://app_user:pw@localhost:5432/placement" \
JWT_SECRET="dev-secret" DEV_FALLBACK=true \
python -m uvicorn app.main:app --reload
```

## Directory structure

```
backend/
├─ app/
│  ├─ main.py          FastAPI app, middleware, router wiring
│  ├─ config.py        pydantic-settings (reads from env / .env)
│  ├─ db.py            engine + tenant_connection() — THE critical file
│  ├─ auth.py          JWT decode → Claims dataclass (injected via Depends)
│  ├─ security.py      bcrypt, JWT issuing, rate limiter
│  └─ routers/
│     ├─ auth_routes.py      Google SSO, password login, claim account, /me
│     ├─ dashboard.py        tenant-scoped stats + funnel
│     ├─ companies.py        company list with registration/placement counts
│     ├─ students_admin.py   CSV import, roster list, activation codes
│     └─ portal.py           student-facing: my applications
├─ db-init/
│  ├─ 01-schema.sql    tables + RLS policies (source of truth)
│  ├─ 02-app-role.sh   creates the non-superuser app_user role
│  └─ 03-seed.sql      demo college, 40 students, 4 companies, realistic funnel
├─ tests/
│  └─ test_google_sso.py   Google SSO path tests (substituted verifier)
├─ requirements.txt
└─ Dockerfile
```

## How tenant isolation works (read this first)

Every request flows through `db.py → tenant_connection(claims)`:

1. Opens a transaction on the connection pool.
2. Runs `SET LOCAL app.role / app.college_id / app.branch_id / app.user_id`
   from the JWT claims.
3. Yields the connection to the route handler.
4. Commits (or rolls back on error).

`SET LOCAL` scopes the GUC to the current transaction only — it cannot leak
to the next request on a pooled connection. Every RLS policy in
`01-schema.sql` reads these GUCs. The app connects as `app_user`, a
non-superuser, so RLS is enforced — superusers bypass it.

**The golden rule:** never open a raw `engine.connect()` in a route handler.
Always use `tenant_connection(claims)`.

## Authentication flows

**Google SSO** (`POST /api/auth/google`): frontend sends a Google ID token →
backend verifies it against Google's certs → email matched to membership
(admin/sub_admin) or roster (student) → first student sign-in auto-creates
and links → returns a scoped JWT.

**Password login** (`POST /api/auth/login`): email + bcrypt-verified password
→ role resolved from memberships or linked student row → scoped JWT.

**Claim account** (`POST /api/auth/claim`): for colleges without Google —
college slug + roll number + activation code → code verified and consumed →
student sets password → account created and linked → scoped JWT.

All three converge on `security.create_token()` which embeds
`{user_id, role, college_id, branch_id}` in the JWT.

## Adding a new endpoint

1. Create `backend/app/routers/your_module.py`.
2. Use `Claims = Depends(get_claims)` and `tenant_connection(claims)`.
3. Register it in `main.py`: `app.include_router(your_module.router)`.
4. If it needs a new table, add it to `01-schema.sql` with the standard RLS
   pattern: `ENABLE` + `FORCE` + policy using `app_role()` / `app_college()`.
5. Write a migration in `migrations/` for existing databases.

## Running tests

```bash
cd backend
PYTHONPATH=. python -m pytest tests/ -v
# or individual: PYTHONPATH=. python tests/test_google_sso.py
```

Tests run against a real local Postgres (seeded) — they are integration
tests, not mocks.
