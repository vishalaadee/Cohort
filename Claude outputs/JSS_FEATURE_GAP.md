# What your college's portal has that Cohort doesn't

Read from the 13 files you uploaded (JSS placement portal — Mysore/Bangalore/Noida,
three colleges on one deployment) and compared against Cohort's actual code.

**Verification status matters here.** I have Cohort's `placement.py`, `portal.py`,
`permissions.py`, `main.py`, and migrations `0008`/`0009` in front of me. I do **not**
have the base schema (`db-init/01-schema.sql`), migrations `0002`–`0007`, or
`auth_routes.py` / `admin_extra.py` / `students_admin.py` / `companies.py` /
`dashboard.py` — those live on your server and were not in the release bundle. So
anything below marked *unverified* is a gap I could not confirm either way, and you
should grep before trusting it.

---

## 1. The four things you named

### JD attachments (up to 3) — **confirmed missing**

Your portal (`admin_routes.py` `add_company`) does this properly:

- `upload_file()` puts each file in S3 under `job_descriptions/{uuid}_{filename}`
  with `ContentDisposition: attachment`
- Stores the three URLs in a `placement_files` table keyed by `cid` (`f1_url`,
  `f2_url`, `f3_url`)
- Passes `file1_url/file2_url/file3_url` into the SES payload so the JD link goes
  out with the announcement email
- `student_routes.py` `/companies-with-files` joins it back for students

Cohort has **nothing** here. Grepping `placement.py` for `attach|jd|upload|s3|boto3`
returns only two `Content-Disposition` headers on CSV/ZIP *downloads*. There is no
file column on `companies`, no attachment table, no S3 client. This needs a
migration plus routes.

One design note before we copy it: three nullable URL columns (`f1_url`, `f2_url`,
`f3_url`) is why "up to 3" is hardcoded. A `drive_attachments` child table keyed by
`(college_id, company_id)` with a row per file costs the same to build, keeps RLS
uniform with the rest of Cohort, and the "max 3" becomes a check the API enforces
rather than a shape the schema locks in.

### Group email set by officers only — **partly built, no write path**

Migration `0009` line 168 already adds the column:

```sql
ALTER TABLE colleges ADD COLUMN IF NOT EXISTS notify_groups jsonb NOT NULL DEFAULT '{}';
-- {"students":{"email":"placements-2027@demo.ac.in","verified_at":"..."},
--  "juniors" :{"email":"students-all@demo.ac.in","verified_at":null}}
```

That is exactly your "up to 2 groups" — `students` and `juniors` — and it already
carries a `verified_at` so an unverified address can't be announced to. `publish_drive`
reads it (lines 243–250) and refuses to send unless `verified_at` is set.

What's missing is the endpoint that *writes* it. There is no such route in
`placement.py`. It may exist in `admin_extra.py` — **check before I add one**:

```bash
grep -rn "notify_groups" backend/app/
```

If nothing comes back, I'll add `GET/PUT /api/notify-groups` gated on
`require_placement_officer` (the same guard `publish_drive` uses), with the email
change resetting `verified_at` to null so a changed address must be re-verified.

Worth noting what your version does here that we should *not* copy: `send_file` and
`update_send_file` in `admin_routes.py` default `email2` to a hardcoded personal
Gmail (`aadeevishal@gmail.com`, `prab7hat@gmail.com`) when the caller omits it. Every
company announcement from those routes silently CCs a personal inbox.

### Google SSO — **probably already built, just unconfigured**

Your live server answered:

```
curl -s localhost/api/auth/config
{"google_client_id":"","dev_fallback":false}
```

A backend with no SSO support wouldn't have a config endpoint that reports a
`google_client_id` at all. The strong likelihood is that `auth_routes.py` already
implements the Google flow and it is returning empty because `GOOGLE_CLIENT_ID` is
unset in `.env`. That would make this a configuration task, not a build task.

I can't confirm it without reading `auth_routes.py` — it wasn't in the bundle. Send it
(or run `grep -n "google\|GOOGLE\|id_token\|oauth" backend/app/routers/auth_routes.py`)
and I'll tell you in one reply whether it's a config change or real work.

### Planner not working — **needs the actual error**

Cohort's planner is `GET /api/calendar` (`placement.py` lines 188–215). Reading it,
the query shape is sound — it unions drive deadlines, drive test dates,
`company_notes`, and your own open reminders for the month, then sorts. Two things
could break it against your database:

1. It selects `n.kind` from `company_notes`. If that column doesn't exist in your
   schema (it's from a migration I can't see), the whole endpoint 500s.
2. `test_date` only came in with `0009`, so drives created before today have it null
   and simply won't appear — which looks like "the planner is empty" rather than an error.

Get me the real signal rather than guessing:

```bash
# in the browser, open the Planner view, then F12 → Network → click the /calendar row
# and on the server:
cd ~/Cohort/infra
docker compose -f docker-compose.aws.yml logs --tail=100 backend | grep -i -A5 "calendar\|traceback"
```

A 500 means the SQL is wrong for your schema; a 200 with `"events": []` means it's a
data problem, not a code one. Those are different fixes.

---

## 2. Everything else worth taking from your portal

Ordered by how much I think it matters, not by effort.

**Blacklist with credits** (`models.py` `Blacklist`: `urn`, `credits`,
`company_count`). A student who no-shows loses credits; at zero they're blocked from
registering, and `student_routes.py` returns "You have been blacklisted" as a
first-class eligibility reason. Cohort has no equivalent — grep for `blacklist`
across everything I have returns nothing. This is the single biggest behavioural gap:
right now Cohort has no way to penalise a no-show, which is the main lever a placement
office actually has over students.

**Absent tracking** (`Absent` table, `(urn, cid)`). Records who didn't turn up to a
specific drive — which is what feeds the blacklist. Also nothing in Cohort.

**Internal remarks on students** (`Remarks` table, staff-written free text keyed to
`urn`). Cohort has no staff-private note on a student. Worth having, and it has to be
officer-only and never exposed on the student's own profile route.

**Company locations** (`CompanyLocation`, a Postgres `ARRAY(String)` per `cid`). Drives
at multi-city companies. Cohort's `companies` has `venue` (text, from `0009`) which is
the interview venue, not the job location — different field, still missing.

**Named evaluation rounds** (`Evaluation_rounds`: `round_1`..`round_7`, commented in
your model as resume screening / OA / tech 1–3 / managerial / HR). Cohort has
`round_progress` and bulk round updates, so the mechanism exists; what your version
adds is the *named stage vocabulary*. Unverified whether Cohort's round names are
configurable per college — check `0006`/`0007`.

**Async email via SQS → Lambda → SES.** Your `add_company` pushes a job onto SQS and
returns immediately; a Lambda does the SES send. Cohort's `publish_drive` appears to
send inline. At one college that's fine. At fifty, a slow SMTP call blocks the request
and a failed send loses the announcement with no retry. This is an architecture
improvement, not a feature, and it's the right call — but it's a Stage-2 problem, not
a now problem.

**Broadcast flag.** `add_company(broadcast: bool)` — announce to every student rather
than only the group. Small, useful, needs to be officer-only for obvious reasons.

**Alumni directory + contact** (`alumni` table, `/alumni/send_email_alumni`). Students
email alumni at a target company. Genuinely valuable and completely absent from Cohort.
Note your implementation sets `MAIL_FROM` to the *student's* address while
authenticating as the placement Gmail — that's spoofing the From header, it'll fail SPF
at most receivers, and it's how a domain gets its mail reputation burned. If we build
this, send from the college address with `Reply-To: student`.

**Feedback reminder to placed students** (`/home/send_feedback_reminder/{cid}`). Cohort
has experiences (`portal.py` `/feedback`) but no nudge to write one. Cheap to add now
that `notification_log` exists — it dedupes by `(college_id, dedupe_key)`, so a
reminder can be made once-per-drive-per-student safely.

**Student self-service marks update** (`/update_marks`, sem5–sem8). Cohort routes this
through `/edit-request` with staff approval instead, which is the better design — a
student editing their own CGPA is exactly the field eligibility keys off. Not a gap;
a deliberate difference. Keep Cohort's.

---

## 3. Things in your portal to deliberately not carry over

These aren't criticisms of code that has been running a real placement season for
years — they're specifically the parts that break when you go from three colleges you
control to fifty you don't.

**Credentials in source.** Two Gmail app passwords (`lczvjvsdgqvzpera`,
`ugpfesadhglobidd`), six hardcoded admin logins (`jssbangalore@admin`,
`PLACEMENT2024`, `HARDWORK2024`, `NOIDASECRETKEY`, `PLACEMENTATNOIDA`,
`PLACEMENTFORJSS@123`), a JWT secret as a default value in `schemas.py`, and DB URLs
with passwords in `database.py` comments. The JWT secret is the worst of these:
anyone holding it can mint a token with `{"role": "admin"}` and get full admin on every
college. Rotate all of it, and rotate the JWT secret last so you only invalidate
sessions once.

**Tenancy by string matching.** `Company.eligible_college_ids` is a comma-separated
string, and isolation is `eligible_college_ids.contains(str(college_id))`. `contains`
is a substring match — college 1 matches `"1"`, but it also matches the `"1"` inside
`"11"`, `"12"`, `"21"`. With three colleges you never hit it. With fifty it is a
cross-tenant leak that shows up as a mystery, not an error. Cohort's RLS approach is
the fix and it's already in place; this is a reason not to port `eligible_college_ids`
along with the features.

**Hardcoded college branching.** `if str(s_college_id) == "3"` then Noida's rules,
`== "2"` Bangalore, else Mysore — with three near-duplicate copies of the eligibility
ladder, each slightly different, plus four near-identical analytics modules
(`analytics.py`, `mysore_`, `bangalore_`, `noida_`). Cohort's policy engine plus
per-drive override is the generalisation of exactly this. Every college you add the old
way is another `elif`.

**Module-level `session = Session(bind=engine)`.** Both `admin_routes.py` and
`student_routes.py` create a session at import and several routes use it instead of the
`get_db` dependency. One shared connection across concurrent requests is how you get a
transaction aborted in one request rolling back another's work.

**`except:` swallowing everything.** `register_into_company` catches bare, rolls back,
and returns `None` — the student sees nothing and no trace is kept. Several routes do
this.

---

## 4. What I need to go further

To write migrations that actually apply against your database and routes that match
your existing patterns, I need the files that weren't in the bundle:

```bash
cd ~/Cohort
zip -r cohort-src.zip backend/app backend/db-init migrations scripts -x '*.pyc' '*__pycache__*'
```

That's small (a few hundred KB) and gives me the base schema, `0002`–`0007`,
`auth_routes.py`, and `admin_extra.py` — which settles the SSO question, the
`notify_groups` write path, and whether blacklist/absent already exist under different
names.
