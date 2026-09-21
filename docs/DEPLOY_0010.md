# Deploying the JD / email / planner release

Your server is already on `0009` with all nine verify checks passing. This adds
migration `0010`, a mailer, JD attachments, officer-settable group addresses,
and the planner fix.

Same shape as last time: restore nothing, unzip on top, stage named paths, push,
pull, migrate, rebuild.

---

## What was verified before this was written

Against a real PostgreSQL 16 with `app_user` as a non-superuser and RLS forced,
not reasoned about:

- `0010` applies clean and **re-applies clean** — it is idempotent.
- 12 RLS checks pass, including the ones that matter:
  - a second college sees **zero** rows of the first in `drive_attachments`,
    `mail_log`, `group_verifications`, `notification_log`, and cannot read the
    first college's group address;
  - a cross-tenant attachment insert is **refused by the RLS policy with an
    error**, not silently dropped;
  - a CR can read JDs but the write policy is admin-only;
  - **a student cannot see the JD of an unpublished drive** — the same class of
    bug as the F-2 draft leak, checked explicitly.
- The mailer was tested against a real SMTP server over a socket: 18/18,
  including that the PDF bytes survive the round trip byte-for-byte, the `From`
  is the college (never a student), and both `text/plain` and `text/html` parts
  are present.

What is **not** verified here: SMTP against your actual mail provider, which
nothing but your credentials can test. Step 5 is where you do that.

---

## 1. On your Mac — unzip and stage

```bash
cd /Users/er.vishalmishra/Documents/GitHub/Cohort
git checkout develop && git pull origin develop

unzip -o ~/Downloads/cohort-0010.zip -d .

git add migrations/0010_attachments_and_mail.sql \
        backend/app/mailer.py \
        backend/app/routers/placement.py \
        backend/app/routers/portal.py \
        frontend/app/app.html \
        scripts/verify-deploy.sql \
        docs/
git status --short
git commit -m "Add JD attachments, outbound mail, officer-set group addresses, planner month navigation"
git push origin develop
```

As before — **not** `git add -A`.

---

## 2. Add the mail settings to `.env` on EC2

Nothing here is optional if you want mail to actually send. With these unset the
app runs fine and every send returns "email is not configured", which the UI
shows you plainly rather than pretending it worked.

```bash
ssh -i portal-pem.pem ubuntu@15.252.205.151
cd ~/Cohort
```

Append to `.env`:

```bash
# --- outbound mail -------------------------------------------------------
SMTP_HOST=email-smtp.ap-south-1.amazonaws.com
SMTP_PORT=587
SMTP_USER=<SES SMTP username>
SMTP_PASSWORD=<SES SMTP password>
SMTP_FROM=placements@yourcollege.ac.in
SMTP_FROM_NAME=Placement Cell
SMTP_STARTTLS=true

# Used for links in emails and for the group-confirmation link.
PORTAL_URL=http://15.252.205.151
```

You already run on AWS, so **SES is the right choice** over a Gmail app
password: Gmail caps you at ~500 recipients a day, will eventually flag a server
sending automated mail, and the app password is a standing credential that grants
full mailbox access if it leaks — which is exactly what happened in the JSS
codebase. SES SMTP credentials only send.

Two things to do in the SES console first: verify `SMTP_FROM` (or the whole
domain — domain verification with DKIM is better, because it also makes your
announcements pass DMARC), and request production access if you are still in the
sandbox, or SES will only deliver to addresses you have individually verified.

`PORTAL_URL` should become your real domain once you have one — it is what
students click in the announcement.

---

## 3. Pull, migrate, rebuild

```bash
cd ~/Cohort
git pull origin develop
set -a && source .env && set +a

./scripts/migrate-rds.sh          # applies 0010 only; 0002-0009 skip

psql "host=$RDS_HOST port=$RDS_PORT dbname=$RDS_DB user=$RDS_ADMIN_USER sslmode=require" \
     -P pager=off -f scripts/verify-deploy.sql
```

Check 1 now expects **9** migrations and check 2 expects **11** tables — both
updated in this release. Checks 10 and 11 are new:

- **10** — no JD is reachable on an unpublished drive.
- **11** — prints each college's announcement address and whether it is
  confirmed. `INFO — not set` is expected right now; you set it in step 5.

```bash
cd ~/Cohort/infra
docker compose -f docker-compose.aws.yml up -d --build backend caddy
curl -s localhost/api/health
```

Then confirm the new routes loaded — `401` means the route exists and auth is
working, `404` means it didn't:

```bash
curl -s -o /dev/null -w "attachments   %{http_code}\n" localhost/api/companies/1/attachments
curl -s -o /dev/null -w "notify-groups %{http_code}\n" localhost/api/notify-groups
```

---

## 4. Turn on Google sign-in — this is configuration, not code

**The SSO code already exists.** `app.html` lines 368–374 load Google's GSI
client, render the button and POST the credential to `/api/auth/google`; your
server already answers `/api/auth/config` with a `google_client_id` field. It is
empty, so the frontend skips rendering the button. That is the whole reason you
don't see it.

Confirm the backend half is really there before doing anything else:

```bash
cd ~/Cohort
grep -n "google\|id_token\|GOOGLE" backend/app/routers/auth_routes.py | head -20
curl -s -o /dev/null -w "%{http_code}\n" -X POST localhost/api/auth/google \
     -H 'Content-Type: application/json' -d '{"credential":"x"}'
```

`401`, `400` or `422` means the endpoint exists and rejected a junk credential —
correct. **`404` means it was never built**, and that is a real (small) piece of
work — send me `auth_routes.py` and I'll write it.

Assuming it exists:

1. Google Cloud Console → **APIs & Services → Credentials → Create OAuth client
   ID → Web application**
2. Authorised JavaScript origins: `http://15.252.205.151` (and your domain later)
3. Copy the client ID, add to `.env`:
   ```bash
   GOOGLE_CLIENT_ID=xxxxxxxx.apps.googleusercontent.com
   ```
4. Restart the backend, then:
   ```bash
   curl -s localhost/api/auth/config
   # {"google_client_id":"xxxx.apps.googleusercontent.com","dev_fallback":false}
   ```

The sign-in page renders the Google button as soon as that field is non-empty.

One thing to decide before you enable it for a pilot college: a Google account
proves *who* someone is, not that they belong to your college. Whatever
`auth_routes.py` does on the callback must match the Google email to an existing
roster row and refuse if there isn't one — otherwise anyone with a Gmail account
can sign in. That is the one thing to read for in the grep above.

---

## 5. Set the group address, then confirm it

In the app: **Settings → Announcements**. The Change button works now — it was
disabled before, which is what you'd noticed.

1. **Set** the student group address — a real group on your college domain
2. Press **Send confirmation** — a link goes to that address
3. Someone who receives mail there opens the link
4. The tag flips to **confirmed**

Publishing will not email anything until that tag says confirmed, and changing
the address clears it. That is deliberate: an address verified once, months ago,
when it was different, is not evidence about the address that's there now.

If **Send confirmation** returns *"Email is not configured on this server"*, step
2 didn't take — re-check `.env` and that you rebuilt.

---

## 6. Walk the new paths

| Do this | You should see |
|---|---|
| Open a draft drive → **JD & files** → Attach a file, pick the JD | `Attached · 2 slots left` |
| Attach a 4th | Button is disabled at 3 |
| Press **Publish** | Drive opens **and** the group is emailed with the JD attached |
| **Emails** tab | A `drive_published` row |
| Attach another JD *after* publishing | Toast says it missed the announcement; a **Resend** button appears |
| Sign in as a student → open that drive | The JD is downloadable |
| Open a *draft* drive's JD as a student | 404 — this is check 10, enforced server-side |
| **Planner → Calendar** | Month name with ← → arrows; move to the month your drives are in |

Then confirm mail actually left the building:

```bash
set -a && source .env && set +a
psql "host=$RDS_HOST port=$RDS_PORT dbname=$RDS_DB user=$RDS_ADMIN_USER sslmode=require" \
  -P pager=off -c \
  "SELECT to_address, subject, status, error, attachments, sent_at
     FROM mail_log ORDER BY sent_at DESC LIMIT 10;"
```

`status='sent'` with `attachments=1` is the JD going out. `status='failed'` puts
the provider's reason in `error` — that column is why this table exists.

---

## 7. Known edges

**A failed send un-publishes nothing.** If the drive publishes but the mail
fails, the drive stays open and the dedupe row is rolled back so pressing
Publish again — the obvious thing to try — actually retries the send rather than
silently doing nothing. The API response carries `mail_status` and `mail_error`.

**`test-reminder` still does not send email.** It writes `notification_log` and
returns, as it did before this release. It is the one place that needs
per-student sending rather than one message to a group, which is a queue, which
is a bigger change than this release. It is now the only route that behaves that
way, and it should be the next thing fixed.

**Attachments live in Postgres, not S3.** Same as resumes. At 5 MB a file and 3
files a drive, a 200-drive season is about 3 GB worst case — fine for RDS, and it
keeps the file under the same RLS as the drive. Revisit if attachments start
dominating your backup size, not before.
