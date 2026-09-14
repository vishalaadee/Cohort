# Run it, check it, ship it

Follow these in order. Each step says what to run and **what you should see**. If you don't see it, stop — the next step will make it worse, not better.

Your setup, which these commands assume: Ubuntu EC2 with an Elastic IP, Postgres on **RDS** (not in Docker), `docker-compose.aws.yml`, Caddy for TLS, `.env` in the repo root, you SSHing from macOS.

---

## What I verified before writing this

I stood up PostgreSQL 16, applied your `01-schema.sql`, your `app_user` role and grants, your seed, and all eight migrations through your own `scripts/migration-lib.sh`. Then I ran every SQL statement in the new code as `app_user` with RLS active. Results:

- All 8 migrations applied clean, in order.
- **Tenant isolation holds.** A second college was created; from college 1, zero rows of college 2 were visible in any of 12 tenant tables.
- **CR branch scoping works** — a `sub_admin` scoped to CSE saw 10 students across exactly 1 branch.
- **Students see only themselves** — 1 student row, 1 application.
- **Reminders are private** — a different admin in the same college saw 0 of mine.
- **The F-6 fix works** — a student sees 1 `round_progress` row (their own); the admin sees all 5. Before `0008` the student saw all 5.
- **Sends are idempotent** — publishing twice and reminding twice both return zero rows the second time.
- **The F-2 leak is real and now fixed** — before: a student query returned 4 drives including 1 unpublished draft. After: 3 drives, 0 drafts.
- All 49 API paths the frontend calls resolve to real backend routes.

What I could **not** run here: `uvicorn` itself, because PyPI is blocked in my sandbox. Step 7 is where you confirm the HTTP layer, and it's why the checks there are specific.

One bug this caught, worth knowing about: `admin_extra.py` and `students_admin.py` mount at **`/api/admin`**, not `/api`. My first draft of `app.html` called them without the prefix, which would have broken the entire admin side at runtime. That's fixed in this zip.

---

## 1. Restore the 41 deleted files — before anything else

Commit `36b46e5` ("new changes") deleted the whole backend app, `backend/Dockerfile`, `requirements.txt`, `db-init/`, the tests, migrations `0002`–`0007`, your landing page, and `docs/INFRA.md`. That's why `portal.py` is missing. `docker compose up --build` cannot work in this state — there's no Dockerfile to build from.

**On your Mac:**

```bash
cd /Users/er.vishalmishra/Documents/GitHub/Cohort
git checkout develop
git fetch origin && git pull origin develop

git diff --name-only --diff-filter=D 64a7a78 HEAD | xargs git checkout 64a7a78 --
```

That restores only files that were deleted. Modified files (`main.py`, `permissions.py`, `app.html`) keep their newer versions; added files (`placement.py`, `0008`, `0009`) are untouched. I tested this exact command on a clone of your repo: 41 files return, nothing new is lost.

**You should see:**

```bash
ls backend/app/routers/
# __init__.py admin_extra.py auth_routes.py companies.py dashboard.py
# placement.py portal.py students_admin.py
```

---

## 2. Unzip this release ON TOP, then stage only these paths

Order matters — restore first (step 1), then unzip, so the release files win.

```bash
unzip -o ~/Downloads/cohort-release.zip -d .

git add backend/app/main.py backend/app/permissions.py \
        backend/app/routers/placement.py backend/app/routers/portal.py \
        frontend/app/app.html migrations/ docs/ scripts/verify-deploy.sql
git add -u                      # picks up the 41 restored files
git status --short | head -20
```

**Do not run `git add -A` after unzipping an overlay** — that is exactly what recorded the 41 deletions last time.

`portal.py` is in this zip **with the draft-drive fix already applied**, so there is no manual `sed` step any more.

```bash
git commit -m "Restore deleted backend; add placement features, migrations 0008-0009, redesigned app"
git push origin develop
```

**Verify the tree is whole before you deploy:**

```bash
test -f backend/Dockerfile && test -f backend/requirements.txt \
 && test -f backend/app/routers/portal.py && test -f backend/app/routers/placement.py \
 && test -f backend/db-init/01-schema.sql \
 && grep -q "WHERE status = 1" backend/app/routers/portal.py \
 && echo "TREE OK — safe to deploy" || echo "STOP — something is missing"
```

Only continue when it prints **TREE OK**.

---

## 3. Connect and check what the server is currently running

```bash
ssh -i ~/.ssh/YOUR-KEY.pem ubuntu@YOUR-ELASTIC-IP
cd ~/Cohort
git log --oneline -1
ls backend/app/routers/
```

If the server still lists `portal.py` etc., it's running the old complete code and nothing is down — good. It will pick up the restore when you pull.

---

## 4. Back up RDS

```bash
cd ~/Cohort
set -a && source .env && set +a

pg_dump "host=$RDS_HOST port=$RDS_PORT dbname=$RDS_DB user=$RDS_ADMIN_USER sslmode=require" \
  -Fc -f ~/cohort-backup-$(date +%F-%H%M).dump

ls -lh ~/cohort-backup-*.dump
```

Prompts for the RDS master password. If `pg_dump` is missing: `sudo apt install -y postgresql-client`.

**You should see** a file of non-zero size. Also take an RDS console snapshot (**RDS → your instance → Actions → Take snapshot**, name it `pre-0009`) — it's free and instant.

---

## 5. Pull the code

```bash
cd ~/Cohort
git pull origin develop
ls backend/app/routers/ && ls backend/Dockerfile backend/requirements.txt
```

**You should see** all eight router files and both build files.

---

## 6. Apply the migrations

Your runner records each in `schema_migrations` and verifies checksums, so already-applied ones are skipped and re-running is safe.

```bash
chmod +x scripts/migrate-rds.sh
./scripts/migrate-rds.sh
```

**You should see** `0008_security_fixes` and `0009_placement_features` applied. `0002`–`0007` showing as already applied is correct.

Then run the verification script that ships in this release:

```bash
psql "host=$RDS_HOST port=$RDS_PORT dbname=$RDS_DB user=$RDS_ADMIN_USER sslmode=require" \
     -f scripts/verify-deploy.sql
```

**You should see PASS on all nine checks:**

```
1. Migrations applied              PASS   (8 versions listed)
2. New tables exist                PASS   (8 tables)
3. Cross-tenant view is gone       PASS
4. Every tenant table has forced RLS   PASS
5. App connects as a non-superuser PASS
6. Buckets seeded for every college    PASS
7. No unpublished drive has registrations  PASS
8. Notification dedupe constraint present  PASS
9. round_progress scoped to the student    PASS
```

Any **FAIL** — stop and fix it before restarting the app. Check 5 failing is the serious one: it means the API is connecting as a role that bypasses row-level security, and tenant isolation is not actually being enforced.

---

## 7. Rebuild and restart

```bash
cd ~/Cohort/infra
docker compose -f docker-compose.aws.yml up -d --build backend caddy
```

`--build` is required — `placement.py` is a new file and the image must be rebuilt to contain it.

**Never run `docker compose down -v`** — `-v` destroys your MinIO, Grafana and Caddy volumes.

Leave `minio`, `prometheus`, `grafana`, `node-exporter`, `postgres-exporter` and `cadvisor` running.

### Confirm the HTTP layer

```bash
curl -s localhost/api/health
```

**Expected:** `{"status":"ok","db":"up","schema":"current"}`

If you get `"schema":"upgrade_required"`, a migration didn't apply — back to step 6. The app deliberately refuses to serve `/api/*` against a half-migrated database.

```bash
docker compose -f docker-compose.aws.yml logs --tail=40 backend
```

**Expected:** startup lines, no tracebacks. A `ModuleNotFoundError: placement` means the image was built before the file arrived — run step 7 again.

```bash
curl -s -o /dev/null -w "buckets      %{http_code}\n" localhost/api/buckets
curl -s -o /dev/null -w "entitlements %{http_code}\n" localhost/api/entitlements
curl -s -o /dev/null -w "admin/policy %{http_code}\n" localhost/api/admin/policy
curl -s localhost/api/auth/config
```

**Expected:** `401` for the first three — the routes exist and authentication is being enforced. A `404` means the router didn't load. `/api/auth/config` should return JSON.

---

## 8. Click through it

Open `http://YOUR-ELASTIC-IP/app`, sign in as the placement officer, and do these six. Each one exercises a different new code path.

| # | Do this | You should see |
|---|---|---|
| 1 | **Drives → Add company / drive** — pick a bucket, answer "any customisation?" **No** | Drive created as a **Draft** |
| 2 | Press **Publish** on it | Flips to **Open**; toast says students weren't emailed (no verified group yet) |
| 3 | Open it → **Who can apply** → add a CGPA condition → **Preview count** | Toast: "N of M students qualify" |
| 4 | **Downloads** → tick columns → **Download CSV** | CSV downloads, opens in Excel with exactly those columns |
| 5 | **Policy & buckets** → set offer rule to **Both**, multiplier 1.5 → Save | Footer reads "higher bucket and pay at least 1.5× their current offer" |
| 6 | Sign out, sign in as a student → **Drives** | Search box present; only eligible drives shown; ticking the box reveals blocked ones **with the reason** |

Then confirm the audit trail is being written:

```bash
psql "host=$RDS_HOST port=$RDS_PORT dbname=$RDS_DB user=$RDS_ADMIN_USER sslmode=require" -c \
"SELECT action, actor_role, created_at FROM audit_log ORDER BY created_at DESC LIMIT 10;"
```

**Expected:** rows for `drive.publish` and `registrations.export`. If it's empty after doing steps 1–4, the new router isn't being hit.

---

## 9. If something breaks

**Roll the app back** — migrations are additive, leave them in place:

```bash
cd ~/Cohort
git log --oneline -5
git checkout <previous-sha> -- backend/app frontend/app
cd infra && docker compose -f docker-compose.aws.yml up -d --build backend caddy
```

**Restore RDS** (only if you must):

```bash
pg_restore -c -d "host=$RDS_HOST port=$RDS_PORT dbname=$RDS_DB user=$RDS_ADMIN_USER sslmode=require" \
  ~/cohort-backup-YYYY-MM-DD-HHMM.dump
```

| Symptom | Cause | Fix |
|---|---|---|
| `failed to read dockerfile` | `backend/Dockerfile` missing | Step 1 restore |
| `ModuleNotFoundError: placement` | Image built before the file arrived | Step 7 again |
| `"schema":"upgrade_required"` | Migration didn't apply | Step 6 |
| `/api/buckets` → 404 | Router not registered | Confirm `main.py` from this zip is in place |
| `/api/admin/policy` → 404 | Wrong prefix somewhere | These live at `/api/admin`, not `/api` |
| Admin screens blank, console 404s | Old `app.html` still cached | Hard-refresh (⌘⇧R) |
| CSV export → 422 | Column not in the server allow-list | Working as intended — pick from the UI list |
| Students see unpublished drives | Old `portal.py` | `grep "WHERE status = 1" backend/app/routers/portal.py` |
| Buckets empty for a college | College created after `0009` ran | Re-run the seed block at the top of `0009` |

---

## 10. Two things in the first week

**Turn on branch protection.** GitHub → Settings → Branches → rule for `main` and `develop`: require a pull request, block force-pushes. The 41-file deletion would have shown up as a diff instead of landing silently. Five minutes, and it's the single highest-value thing on this page.

**Set the student group address.** Publishing announces a drive by email, but only once a verified group address exists. Until then publishing works and simply doesn't email — the UI tells you so. The verification step is deliberate: an unverified address would let an admin point every announcement outside the college.
