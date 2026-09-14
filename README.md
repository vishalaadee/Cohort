# Cohort — release bundle

> ## ⚠ Read `docs/DEPLOY_EC2.md` section 1 first
>
> Commit `36b46e5` on `develop` deleted 41 files — the whole backend app,
> `backend/Dockerfile`, `db-init/`, the tests, migrations `0002`–`0007`, and
> `docs/INFRA.md`. **Do not deploy from `develop` as it stands** — the backend
> image cannot even build. Everything is recoverable from git history and the
> restore is one command, in section 1 of that doc.

**This zip is an OVERLAY.** It contains only the files that change. Unzip it
into the repo, then `git add` the specific paths below — `git add -A` after
unzipping is what recorded those deletions last time.

```bash
unzip -o ~/Downloads/cohort-release.zip -d .
git add backend/app/main.py backend/app/permissions.py \
        backend/app/routers/placement.py backend/app/routers/portal.py \
        frontend/app/app.html migrations/ docs/ scripts/verify-deploy.sql
git add -u          # the restored files
```

Four files **replace** existing ones (`main.py`, `permissions.py`, `portal.py`,
`app.html`); everything else is new. `portal.py` ships with the draft-drive
leak already fixed, so there is no manual edit step.

### Verified, not assumed

This release was run against a real PostgreSQL 16: your schema, your role
grants, your seed, all eight migrations through your own migration runner,
then every new SQL statement executed as `app_user` with RLS active. Tenant
isolation, CR branch scoping, student self-scoping, reminder privacy, the
F-6 round_progress fix and send idempotency were all confirmed with a second
college present. `scripts/verify-deploy.sql` reruns those checks against your
database after you deploy — nine checks, all should print PASS.

Written against the real code on `develop` (commit `4e3f67c` plus your local vision-docs commit), September 2026. Where a document makes a claim about the codebase, it was verified by reading the file.

---

## What's in here

```
docs/
  ARCHITECTURE.md      Current state (verified), target architecture, 8 ADRs,
                       the Phase 1/2 seams, scaling triggers, sequenced plan
  DOMAIN_MODEL.md      ERD, entity dictionary, state machines, the full
                       permission model incl. the ungrantable CR set
  USE_CASES.md         8 actors, 47 use cases with phase + current status,
                       7 sequence diagrams
  SECURITY_REVIEW.md   10 findings from reading the actual code, with fixes
  GTM_ROLLOUT.md       ICP, the accreditation wedge, staged rollout with
                       gates, company-side cold-start solve, pricing, metrics
  EXPANSION.md         Late-stage other verticals (read once, then put down)
  FEATURE_SPEC.md      The Sept 2026 feature brief: data model deltas,
                       security analysis per feature, system design
                       principles, metrics, capability checklist

  DEPLOY_EC2.md        Every command to ship this to EC2, in order

migrations/
  0008_security_fixes.sql      Drops the cross-tenant view, tightens
                               round_progress RLS, adds audit_log,
                               consent_events, score_history, perm_epoch
  0009_placement_features.sql  Buckets with aliases, reminders, export
                               templates, notification log, entitlements,
                               per-drive customisation, junior/final-year

backend/app/
  main.py              REPLACES — registers the new router, tightens CORS
  permissions.py       REPLACES — adds the officer-only capability set
  routers/placement.py NEW — buckets, reminders, calendar, publish,
                       test reminder, bulk round updates, CSV export,
                       resume zip, entitlements

frontend/
  app/app.html         REPLACES — the redesigned app, wired to the real API
  ui-redesign.html     Static mockup of the same design, no backend needed
  UI_NOTES.md          Design decisions and the role colour system
```

Markdown files contain Mermaid diagrams, which GitHub renders natively once pushed.

---

## Start here, in this order

**1. Open the mockup** — double-click `frontend/ui-redesign.html`. No server, no build. The top bar switches between Admin, CR, Student and Junior, each with its own accent colour, and between dark and light.

**2. Read `docs/SECURITY_REVIEW.md`** — it's the shortest document and the only one with items that should be done before a pilot college touches the system. Three of them are a few lines of code each.

**3. Skim `docs/USE_CASES.md` §2** — the catalogue of 47 use cases with what already exists. The useful surprise is how short the P0 gap list is.

**4. Then `docs/FEATURE_SPEC.md`** — the September feature brief worked through: what each feature costs in security, what it adds to the schema, and the build order.

**5. Then `docs/GTM_ROLLOUT.md` §1 and §3** — the calendar problem and the accreditation wedge. These change what you build next more than anything in the architecture doc.

---

## Running things

### The mockup

```
open frontend/ui-redesign.html
```

That's it — it's a single self-contained file with static demo data drawn from your own seed (Demo Institute of Technology, Rubicon/Nova/Kessel/Beacon, the real round names, the real CR capability keys, and eligibility strings phrased exactly the way `eligibility.py` generates them).

### The existing stack, unchanged

```bash
cp .env.example .env          # set JWT_SECRET + passwords
cd infra
docker compose up -d --build
```

`http://localhost` for the landing page, `http://localhost/app` to sign in. Seeded demo credentials are `admin@demo.ac.in` / `demo1234`. The fuller walkthrough in `QUICKSTART.md` (Greenfield National College, roster import, the Sanjay claim flow) still applies unchanged.

### Applying migration 0008

Your migration runner (`scripts/migration-lib.sh`) picks up `migrations/[0-9][0-9][0-9][0-9]_*.sql` automatically, records each in `schema_migrations`, and verifies checksums — so just place the file and run.

**On RDS:**
```bash
./scripts/migrate-rds.sh
```

**Locally — fresh database** (the init hook only runs on an empty data directory):
```bash
cd infra
docker compose down -v          # WARNING: deletes local data
docker compose up -d --build
```

**Locally — keeping existing data:**
```bash
docker exec -i infra-db-1 psql -U postgres -d placement < migrations/0008_security_fixes.sql
```

Then confirm the app is happy — `main.py` blocks `/api/*` with a 503 when the schema is behind:
```bash
curl -s localhost/api/health
# {"status":"ok","db":"up","schema":"current"}
```

Note that `0008` **drops** the `recruiter_candidates` view. Nothing references it (verified by grep across `backend/` and `frontend/`), and `SECURITY_REVIEW.md` F-1 explains why it shouldn't exist until there's a recruiter console to consume it. The correct `security_invoker` version is included, commented, for that day.

### Before applying it, run this one check

F-1's severity depends on who owns that view on *your* database:

```sql
SELECT c.relname, pg_get_userbyid(c.relowner) AS view_owner,
       r.rolsuper, r.rolbypassrls
FROM pg_class c JOIN pg_roles r ON r.oid = c.relowner
WHERE c.relname = 'recruiter_candidates';
```

If `rolsuper` or `rolbypassrls` is true, that view was a live cross-tenant read path — worth knowing either way.

### Tests

```bash
cd backend
pip install -r requirements.txt
pytest tests/ -v
```

`SECURITY_REVIEW.md` ends with two tests worth adding — a per-table isolation test driven off `information_schema`, and a test that fails the build if any `/api/` route lacks an explicit authorization decision. Both close whole categories of future bug rather than single instances.

---

## Two things worth knowing before you read the docs

**The backend is further along than the vision document assumes.** Pooled multi-tenancy with forced RLS, a safe rule-tree evaluator, a policy engine, configurable CR capabilities, a schema-version guard, uniform error envelopes. The honest blocker to a pilot is correctness and onboarding, not features.

**Some Phase 2 already shipped.** Migration `0005` added consent flags, coding profiles, a computed talent score and a recruiter view — that's talent-network infrastructure, not placement-OS infrastructure, and `CLAUDE.md` says not to build it yet. `ARCHITECTURE.md` §7 recommends keeping most of it and reclassifying it explicitly as "Phase 1.5 — the data foundation", with hard rules about what it may not do, rather than pretending the rule was followed. The recruiter view is the one piece with no Phase 1 justification, which is why `0008` drops it.
