# Operations guide — Google SSO, onboarding, and using the app

`STARTUP_GUIDE.md` gets the infrastructure running. This guide covers what
happens on top of it: configuring Google sign-in, onboarding a college, the
two student onboarding paths, and how each role uses the app day to day.

---

## 1. Set up "Sign in with Google" (once, ~10 minutes)

Google sign-in needs an OAuth client ID from Google Cloud. It's free at any
realistic scale for this app.

1. Go to **console.cloud.google.com** → create a project (e.g. `cohort-prod`).
2. **APIs & Services → OAuth consent screen**: choose **External**, fill in
   the app name (Cohort), support email, and your domain. Scopes: the defaults
   (`email`, `profile`, `openid`) are all this app uses. Publish the app —
   while it's in "Testing" status only listed test users can sign in.
3. **APIs & Services → Credentials → Create credentials → OAuth client ID**:
   - Application type: **Web application**
   - **Authorized JavaScript origins** — add every origin the app is served
     from, exactly: `https://yourdomain.com`, and for local dev
     `http://localhost` (and `http://localhost:8080` if you use another port).
     No paths, no trailing slashes. The Google button silently refuses to
     render on origins not in this list — it's the most common setup gotcha.
   - Redirect URIs: none needed (the app uses Google Identity Services'
     ID-token flow, not a redirect flow).
4. Copy the **Client ID** (ends in `.apps.googleusercontent.com`) into `.env`
   as `GOOGLE_CLIENT_ID`, and restart the backend.

Leave `GOOGLE_CLIENT_ID` empty and the Google button simply doesn't render —
password + activation-code onboarding still works fully. That's also the
switch for a college that doesn't want SSO at all.

**How verification works:** the frontend gets an ID token from Google's
button and posts it to `/api/auth/google`. The backend verifies the token's
signature against Google's published certificates and checks the audience is
your client ID — no client secret is involved, nothing is stored from Google
beyond the account's stable `sub` identifier.

---

## 2. Onboarding a college (Owner + Admin, ~30 minutes end to end)

Right now college creation is an Owner action done in SQL (a self-serve
signup screen is on the roadmap — the schema already supports it via
`colleges.status='pending'`).

**Step 1 — Owner creates the tenant and its first admin.** Connect with
DBeaver (see STARTUP_GUIDE §5) and run, adjusting values:

```sql
SET app.role = 'owner';   -- required: RLS applies even to the master account

INSERT INTO colleges (name, slug, email_domain, status)
VALUES ('JSS Science & Technology University', 'jssstu', 'sjce.ac.in', 'active');

-- the placement officer's login (password path); for Google-only, insert the
-- user with password_hash = NULL — they'll sign in with Google directly
INSERT INTO users (email, full_name, password_hash)
VALUES ('placements@sjce.ac.in', 'Placement Officer',
        NULL /* or a bcrypt hash — generate one with:
               python3 -c "import bcrypt;print(bcrypt.hashpw(b'THEIRPASSWORD',bcrypt.gensalt()).decode())" */);

INSERT INTO memberships (user_id, college_id, role)
VALUES (currval('users_id_seq'), currval('colleges_id_seq'), 'admin');
```

`email_domain` is what lets Google sign-ins from `@sjce.ac.in` resolve to this
college. `slug` is what students type in the Claim account form.

**Step 2 — Admin imports the roster.** The admin signs in → **Import roster**
→ drops a CSV with columns:

```
roll_no,email,full_name,branch_code,cgpa,backlogs
01JST21CS001,arya@sjce.ac.in,Arya Sharma,CSE,8.7,0
```

Rules the import applies (all reported back in the result screen):
- bad rows (invalid email, non-numeric CGPA) are listed with line numbers;
  good rows import anyway
- roll numbers that already exist are skipped, never overwritten
- unknown `branch_code` values create the branch automatically
- every imported student gets an **activation code** — download the CSV of
  codes from the result screen (or later from Students → *Download unclaimed
  activation codes*)

**Step 3 — (optional) add Sub-Admins (branch CRs).** Same SQL shape as the
admin, with `role = 'sub_admin'` and a `branch_id`. Their entire view of the
app is automatically fenced to that branch by RLS.

---

## 3. Student onboarding — two paths, one outcome

**Path A — the college uses Google (Workspace for Education or students have
Gmail addresses on the roster):** the student opens `/app` → **Continue with
Google**. Their verified Google email is matched against the roster; on first
sign-in their account is created, linked, and marked verified automatically.
Zero manual approvals, zero passwords to manage. If their Google email isn't
on the roster they get told exactly that — the fix is the admin adding them
to the roster, not a support queue.

**Path B — no Google accounts:** the placement cell distributes each
student's activation code (from the import). The student opens `/app` →
**Claim account** tab → enters college code (the slug, e.g. `jssstu`), roll
number, activation code, and chooses a password. The claim consumes the code
(it can't be reused), links the roster row, and signs them in. From then on
it's normal email + password sign-in.

Both paths converge on the same thing: a roster-verified student with a
scoped login. A student can also use Path B first and later sign in with
Google — the accounts unify on email.

**Security notes for the cell:** distribute codes privately (email merge or
printed slips), not in a public group — a code plus a roll number is what
claims the account. Codes are only shown once at import and thereafter only
to admins via the unclaimed-codes download, which empties as students claim.

---

## 4. Using the app, role by role

**Admin (placement officer)** — lands on the Dashboard: live student /
company / application counts, placement rate, the round-by-round pipeline
funnel, and per-drive registered/placed numbers. **Students** lists the
roster with search and each student's login status (active vs not claimed) —
that status column is effectively your onboarding progress tracker.
**Import roster** is repeatable all season: re-running a corrected CSV only
adds what's new. **Companies** shows every drive with tier, package, and
eligibility.

**Sub-Admin (branch CR)** — the same screens, automatically limited to their
branch by row-level security. They can watch their branch's onboarding
status and pipeline; they cannot import rosters (admin-only) or see sibling
branches.

**Student** — lands on **My placements**: each application with its company,
package, current interview stage, and outcome. **Drives** lists companies
with tier, package, and eligible branches. (Self-service registration and
interview-experience browsing are the next build items — the data model and
seed data already carry them.)

**Owner (you)** — signs in like anyone else (create yourself a membership
with `role='owner'`, `college_id=NULL`) and sees across every tenant. Day to
day you'll mostly be in Grafana and DBeaver rather than the app UI.

---

## 5. Session + account mechanics worth knowing

- Sign-ins issue an 8-hour JWT stored in the browser; after expiry the app
  returns to the sign-in screen. Adjust via `JWT_EXPIRY_HOURS`.
- Login and claim endpoints are rate-limited (10 attempts / 5 min per
  IP+email) in-process. Good enough for one box; move to Redis-backed
  limiting when you scale out.
- Failed claims return one deliberately vague message — the API never
  confirms which of college / roll number / code was wrong.
- There is no self-service password reset yet. Interim procedure: the admin
  asks you (owner) to clear the user's `password_hash` and set a fresh
  `activation_code` on their student row, and the student claims again. Build
  proper email-based reset before scaling past the pilot.

---

## 6. Pre-launch checklist (supersedes earlier lists)

- [ ] `GOOGLE_CLIENT_ID` set (or intentionally empty) and origins configured
- [ ] `DEV_FALLBACK` is `false` in production `.env` — with it true,
      unauthenticated requests act as the demo admin
- [ ] Demo credentials removed: delete the seed users/rows or change their
      passwords (`admin@demo.ac.in` / `student1@demo.ac.in` ship with known
      passwords for demos only)
- [ ] Every secret in `.env` rotated from the example values
- [ ] JWT_SECRET is long and random (`openssl rand -hex 32`)
- [ ] Backups verified restorable (STARTUP_GUIDE §10)
- [ ] DPDP Act review done before onboarding real students beyond the pilot
