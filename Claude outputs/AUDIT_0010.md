# End-to-end audit of the 0010 release

You asked whether I removed working code. Short answer: **no — nothing was
removed.** But you were right to make me check, because the audit found six
real bugs in what I added, one of which made the whole feature dead on arrival.

This documents how that was established rather than asserted.

---

## 1. Was any of your working code removed?

I found the pristine pre-0010 bundle (`cohort-release.zip`, the one you already
deployed) and diffed against it rather than trusting my own memory of what I
changed.

| File | Original | Now | Deleted lines |
|---|---|---|---|
| `placement.py` | 659 | 1070 | **8** |
| `portal.py` | 345 | 393 | **1** |
| `app.html` | 1700 | 1866 | **14** |
| `main.py` | 85 | 85 | 0 — untouched |
| `permissions.py` | 159 | 159 | 0 — untouched |

Every one of those 23 deleted lines accounted for:

- **1 line** in each of `placement.py` / `portal.py` — the `from fastapi import …`
  line, replaced by the same line plus `Response` / `UploadFile`.
- **6 lines** inside `publish_drive`, which I rewrote deliberately. Checked
  statement by statement: every guard (404 / already-published / closed), the
  `UPDATE companies`, the `notification_log` insert and all four original
  return keys are present and unchanged.
- **1 line** — the drive tab array, replaced by the same array plus `JD & files`.
- **5 lines** — the calendar block. `KIND`, the event map, `setView` and
  `tabBar` are byte-identical; only the month parameter and nav were added.
- **8 lines** — the Settings announcements block, where the **Change** button
  was `disabled` and a note said it was "done by your platform contact during
  onboarding". That was the thing you'd flagged as missing. The "Personal
  details in group emails" row next to it was *not* touched.

Then a symbol-level check, which is the part that actually proves it:

```
placement.py   routes    16 -> 23    lost: NONE
               functions 22 -> 33    lost: NONE
portal.py      routes    11 -> 13    lost: NONE
               functions 15 -> 17    lost: NONE
app.html       functions 48 -> 54    lost: NONE
               declarations 146 -> 159  lost: NONE
               API endpoints called 49 -> 55  lost: NONE
```

`_safe_slug` deserves a specific mention because I stopped using it for
attachments: it is **still defined and still used by its three original
callers** — the CSV export filename, the resume-ZIP folder name, and the
per-student filename inside that ZIP. I added a separate helper rather than
changing its behaviour underneath those.

---

## 2. What the audit found wrong — in my new code

### F-1 (critical) — the group confirmation link could never work

`GET /notify-groups/{key}/verify` is opened by whoever receives mail at the
group address. There is no logged-in user, so it used `engine` directly instead
of `tenant_connection`.

That means no `app.college_id` is set, so `app_college()` is `NULL`, so the RLS
policy on `group_verifications` evaluates to `NULL`, so the `UPDATE` matched
**zero rows**. Proven against the database:

```
context: app_role=  app_college=NULL
rows VISIBLE to the verify endpoint: 0
rows the verify UPDATE would match:  0
```

Every confirmation link would have failed as "expired or already used". The
address could never be confirmed, so `publish_drive` would never send, so the
JD would never reach a student. The entire chain was dead.

My earlier test missed it because I ran the SQL *with* `app.college_id` set — I
tested the query, not the context the endpoint actually runs in. That is the
exact mistake worth naming.

**Fixed** with `consume_group_verification()`, a `SECURITY DEFINER` function in
`0010`. It is the only way in, gated on a 256-bit single-use token, writes two
rows, returns no secret, and is pinned with `SET search_path = public` so a
caller who can create objects cannot shadow a table name inside a definer-rights
function. Verified in the real no-tenant-context: valid token accepted, expired
rejected, replay rejected, wrong group rejected, unknown group rejected, address
changed since issue rejected — and the session **cannot list tokens at all**,
only consume one it already holds.

### F-2 (high) — downloaded files lost their extension

`_safe_slug` collapses every non-alphanumeric to a hyphen, including the dot. It
is correct for what it was written for (a company name, where the caller appends
`.csv`) and wrong for a name that carries its own extension:

```
'rubicon-sde1-jd.pdf'  ->  'rubicon-sde1-jd-pdf'
```

The officer would download a file the operating system could not open. Worse,
`portal.py` had a *different* inline sanitiser, so the same file reached the
student as `rubicon-sde1-jd.pdf` and the officer as `rubicon-sde1-jd-pdf`.

**Fixed**: one `safe_filename()` in `backend/app/attachments.py`, used by both.
It takes the basename under both separators, keeps or derives the extension,
and forces the extension to match the stored MIME type — so a file stored as
`cmd.exe` with a PDF body downloads as `cmd.pdf`, describing what is actually
inside it. 14 cases tested including path traversal, a name that is only dots, a
Devanagari filename, and `evil"; filename="x.exe` (the quote is stripped, so it
cannot break out of the `Content-Disposition` header).

### F-3 (high) — the 3-attachment cap could be breached

`upload_attachment` read the count, decided in Python, then inserted. Two
concurrent uploads both read 2, both passed, both inserted. Demonstrated with
two real concurrent sessions:

```
WITHOUT FOR UPDATE: {'x0':'stored','x1':'stored'}       final=4   cap BREACHED
WITH    FOR UPDATE: {'x0':'stored','x1':'refused(409)'} final=3   cap held
```

**Fixed** with `SELECT … FROM companies WHERE id = :c FOR UPDATE`, which
serialises writers to that one drive.

### F-4 (medium) — Publish told the officer to fix the wrong thing

I changed `announced` to mean "mail actually sent" (it previously meant "log row
written") without updating the consumer. So when the address *was* set and
verified and SMTP simply refused us, the toast said:

> "Published. Set a verified group address in Settings to announce it by email."

**Fixed**: the toast now distinguishes sent / failed-with-reason / email-not-
configured / set-but-unconfirmed / not-set, and surfaces `mail_error`.

### F-5 (low) — both group rows could render as "Student group address"

The row label was keyed off `g.label` from the API response. With the
`.catch(()=>({}))` fallback, `g` is `{}` and both rows fell through to the same
label. **Fixed** by keying off `key`, which is always correct.

### F-6 (low) — a malformed month 500'd the calendar

`Query(pattern=r"^\d{4}-\d{2}$")` accepts `2026-13`, which reaches `strptime`
and raises. Pre-existing, but I made the parameter reachable from the UI for the
first time. **Fixed**: now a 422.

Also normalised `mailer._conf` / `mailer.conf` to a single public name, and
switched the Settings wiring from `setTimeout(…, 0)` to the `wire` pattern the
rest of the file uses.

---

## 3. What is verified, and how

Against real PostgreSQL 16, as `app_user` — a **non-superuser**, so RLS actually
applies — on a database dropped and rebuilt from scratch.

**Migration**: applies clean on a virgin database, and re-applies clean
(idempotent).

**12 RLS checks**, all passing:

- a second college sees **zero** rows of the first across `drive_attachments`,
  `mail_log`, `group_verifications`, `notification_log`, and cannot read the
  first college's group address;
- a cross-tenant insert is **refused with an error**, not silently dropped;
- **a student cannot see the JD of an unpublished drive** — the same class as
  the F-2 draft leak;
- publish dedupe holds; a failed send rolls the dedupe row back so retry works,
  while the `mail_log` row recording the failure survives.

**CR restrictions proven server-side**, not merely hidden in the UI:

```
B1 CR insert attachment : PASS - refused by RLS
B2 CR set group address : PASS - refused by RLS
B3 CR issue token       : PASS - refused by RLS
```

**Mailer**: 18/18 over a real SMTP socket — PDF bytes survive byte-for-byte,
`From` is the college and never a student, both `text/plain` and `text/html`
parts present, `Auto-Submitted: auto-generated` so a mailing list does not
auto-reply.

**Syntax**: Python compiles; JavaScript passes `node --check`.

---

## 4. Two things left deliberately unfixed

**The SMTP send happens inside the open database transaction.** If the mail
server hangs, the 15-second timeout holds a connection and a row lock on that
drive for 15 seconds. At one college, with one message per publish, this is
fine and it buys you an honest answer about whether the mail left. It stops
being fine when sending is per-student, which is the same change that turns
`test-reminder` into a real sender — one job, later, not two half-jobs now.

**`test-reminder` still does not send email.** Unchanged from before this
release. It is now the only route that writes `notification_log` and stops
there, which makes it the obvious next thing.

---

## 5. Still outstanding on your side

- **Rotate the credentials from the JSS upload** — two Gmail app passwords, six
  hardcoded admin logins, and the JWT secret. The JWT secret is the urgent one:
  anyone holding it can mint `{"role":"admin"}` for every college. Rotate it
  last so you invalidate sessions once.
- **The SSO check** — §4 of `DEPLOY_0010.md`. The frontend half is already
  built and dormant because `google_client_id` is empty.
