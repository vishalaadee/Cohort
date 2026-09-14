# Deploying this release to EC2

You're on macOS, connecting to EC2 over SSH. This is every command, in order, with what to check after each one.

Nothing here is destructive to your data. The one command that would be (`docker compose down -v`) is flagged where it appears, and you don't need it.

---

## What's in this release

| File | Where it goes | What it is |
|---|---|---|
| `migrations/0008_security_fixes.sql` | `migrations/` | Security fixes — drops the cross-tenant view, tightens `round_progress`, adds `audit_log`, `consent_events`, `score_history` |
| `migrations/0009_placement_features.sql` | `migrations/` | Buckets, reminders, export templates, notification log, entitlements, junior/final-year split |
| `backend/app/routers/placement.py` | `backend/app/routers/` | **New file** — buckets, reminders, calendar, publish, test reminder, bulk round updates, CSV export, resume zip |
| `backend/app/permissions.py` | `backend/app/` | **Replaces** the existing file — adds the officer-only capability set |
| `backend/app/main.py` | `backend/app/` | **Replaces** the existing file — registers the new router, tightens CORS |
| `frontend/app/app.html` | `frontend/app/` | **Replaces** the existing file — the whole redesigned app |

Two small edits you make by hand are in step 3.

---

## 0. Before you start — on your Mac

Get the files onto EC2. Two ways; the first is better because it leaves a record.

**Option A — through git (recommended).** Unzip into your local repo, commit, push, then pull on the server.

```bash
cd /Users/er.vishalmishra/Documents/GitHub/Cohort
unzip -o ~/Downloads/cohort-blueprint.zip -d .
git checkout develop
git add migrations backend frontend docs
git commit -m "Placement features: buckets, reminders, exports, publish flow, redesigned app"
git push origin develop
```

**Option B — copy straight up with scp.** Use this if you don't want to push yet.

```bash
cd ~/Downloads && unzip -o cohort-blueprint.zip -d cohort-release
scp -i ~/.ssh/YOUR-KEY.pem -r cohort-release/* ubuntu@YOUR-EC2-IP:/home/ubuntu/Cohort/
```

Replace `YOUR-KEY.pem`, `YOUR-EC2-IP` and the path if your repo lives elsewhere on the server.

---

## 1. Connect and take a backup

```bash
ssh -i ~/.ssh/YOUR-KEY.pem ubuntu@YOUR-EC2-IP
cd ~/Cohort
```

**Back the database up first.** Two minutes now, versus a bad afternoon later.

```bash
# If your database is RDS:
pg_dump "host=$RDS_HOST port=5432 dbname=placement user=$RDS_ADMIN_USER sslmode=require" \
  -Fc -f ~/cohort-backup-$(date +%F-%H%M).dump

# If Postgres runs in Docker on this box:
docker exec infra-db-1 pg_dump -U postgres placement \
  | gzip > ~/cohort-backup-$(date +%F-%H%M).sql.gz

ls -lh ~/cohort-backup-*        # confirm the file is not zero bytes
```

If you used Option A, pull the code now:

```bash
git checkout develop && git pull origin develop
```

---

## 2. Check what you're about to change

```bash
git status
git log --oneline -3
ls -l migrations/0008_security_fixes.sql migrations/0009_placement_features.sql
ls -l backend/app/routers/placement.py
```

All four files should be there.

---

## 3. Two edits by hand

**Edit 1 — stop draft drives leaking to students.** `/api/me/drives` currently returns every drive including unpublished ones, so a student can see a company you haven't committed to. One line:

```bash
sed -i 's/FROM companies ORDER BY package DESC NULLS LAST/FROM companies WHERE status = 1 ORDER BY package DESC NULLS LAST/' \
  backend/app/routers/portal.py

grep -n "FROM companies WHERE status = 1" backend/app/routers/portal.py
```

That grep must print one line. If it prints nothing, open the file and add `WHERE status = 1` to the `drives = conn.execute(...)` query in `my_drives` yourself.

**Edit 2 — optional, only if you serve the frontend from another domain.** Add one line to `backend/app/config.py` inside the `Settings` class:

```python
    allowed_origins: str = ""     # comma-separated; empty means same-origin only
```

Skip this if Caddy serves both the site and the API, which is the normal setup.

---

## 4. Apply the migrations

Your runner (`scripts/migration-lib.sh`) picks up `migrations/NNNN_*.sql` in order, records each in `schema_migrations`, and verifies checksums — so an already-applied migration is skipped, and running twice is safe.

**If your database is RDS:**

```bash
./scripts/migrate-rds.sh
```

It prompts for the RDS master password. You should see `0008_security_fixes` and `0009_placement_features` applied.

**If Postgres runs in Docker on this box:**

```bash
docker exec -i infra-db-1 psql -U postgres -d placement < migrations/0008_security_fixes.sql
docker exec -i infra-db-1 psql -U postgres -d placement < migrations/0009_placement_features.sql
```

Confirm both landed:

```bash
docker exec -i infra-db-1 psql -U postgres -d placement -c \
  "SELECT version, applied_at FROM schema_migrations ORDER BY version;"
```

(For RDS, run the same query with `psql` against RDS instead.)

### One thing to check before 0008

`0008` drops the `recruiter_candidates` view. Nothing in the code reads it, but it's worth knowing whether it was actually a cross-tenant read path on your database:

```bash
docker exec -i infra-db-1 psql -U postgres -d placement -c \
  "SELECT pg_get_userbyid(c.relowner) AS owner, r.rolsuper, r.rolbypassrls
     FROM pg_class c JOIN pg_roles r ON r.oid=c.relowner
    WHERE c.relname='recruiter_candidates';"
```

If `rolsuper` or `rolbypassrls` came back `t`, that view was readable across every college. It's gone after the migration either way.

### Verify the new tables exist

```bash
docker exec -i infra-db-1 psql -U postgres -d placement -c "\dt buckets|reminders|export_templates|notification_log|entitlements|audit_log"
docker exec -i infra-db-1 psql -U postgres -d placement -c "SELECT key,label FROM buckets ORDER BY sort_order;"
```

The second should list Tier 1, Tier 2, Dream, Core, Internship — seeded automatically for each college.

---

## 5. Rebuild and restart

```bash
cd ~/Cohort/infra

# AWS setup:
docker compose -f docker-compose.aws.yml up -d --build backend caddy

# Single-box setup:
docker compose up -d --build backend caddy
```

`--build` matters: `placement.py` is a new file and the image has to be rebuilt to include it.

**Do not run `docker compose down -v`.** The `-v` deletes your database volume.

---

## 6. Verify

```bash
curl -s localhost/api/health
```

Expected:

```json
{"status":"ok","db":"up","schema":"current"}
```

If you get `"schema":"upgrade_required"`, a migration didn't apply — go back to step 4. The app deliberately refuses to serve `/api/*` against a half-migrated database rather than throwing confusing 500s.

Check the new endpoints answer:

```bash
docker compose logs --tail=40 backend         # no tracebacks on startup
curl -s -o /dev/null -w "%{http_code}\n" localhost/api/buckets    # 401 without a token is correct
```

`401` is the right answer there — it means the route exists and authentication is being enforced.

Then open the site in a browser, sign in as the placement officer, and walk these:

1. **Drives → Add company / drive** — pick a bucket, answer "any customisation?" with **No**. It should create a draft.
2. **Drives** — the new drive shows as *Draft*. Press **Publish**. It should flip to *Open*.
3. Open the drive → **Who can apply** — add a CGPA condition, press **Preview count**.
4. **Downloads** — tick a few columns, **Download CSV**. The file should open in Excel with exactly those columns.
5. **Policy & buckets** — set the offer rule to **Both** with a 1.5 multiplier and save.
6. Sign in as a student — **Drives** should show a search box, only eligible drives by default, and the reason for each blocked one when you tick the box.

---

## 7. If something looks wrong

**Roll the backend back** (the database migrations are additive and safe to leave in place):

```bash
cd ~/Cohort
git log --oneline -5
git checkout <previous-commit-sha> -- backend/app frontend/app
cd infra && docker compose up -d --build backend caddy
```

**Restore the database** (only if you need to):

```bash
# RDS
pg_restore -c -d "host=$RDS_HOST port=5432 dbname=placement user=$RDS_ADMIN_USER sslmode=require" \
  ~/cohort-backup-YYYY-MM-DD-HHMM.dump

# Docker
gunzip -c ~/cohort-backup-YYYY-MM-DD-HHMM.sql.gz | docker exec -i infra-db-1 psql -U postgres -d placement
```

**Common problems**

| What you see | Cause | Fix |
|---|---|---|
| `"schema":"upgrade_required"` | A migration didn't apply | Re-run step 4, check `schema_migrations` |
| `ModuleNotFoundError: placement` | Image built before the file was copied | `docker compose up -d --build backend` again |
| `/api/buckets` returns 500 | `0009` not applied | Apply `0009` |
| Buckets list is empty for a college | College created after the migration ran | Insert its five rows, or re-run the seed block at the top of `0009` |
| Students see drives you haven't published | Edit 1 in step 3 wasn't applied | Re-run that `sed`, rebuild |
| CSV export returns 422 | A column key isn't in the server-side allow-list | That's working as intended — pick columns from the UI list |

---

## 8. After it's live

Two things worth doing in the first week.

**Set the student group address.** Publishing a drive announces it by email, but only once a verified group address exists. Until then publishing still works, it just doesn't email anyone — the UI says so. Verification is deliberate: an unverified address means an admin could point every announcement outside the college.

**Watch `audit_log`.** Every publish, export, bulk update and resume download now writes a row:

```bash
docker exec -i infra-db-1 psql -U postgres -d placement -c \
  "SELECT action, actor_role, detail, created_at FROM audit_log ORDER BY created_at DESC LIMIT 20;"
```

If that table stays empty after you've used the app, the new router isn't being hit — check step 5.
