# What's next

**Where you are:** `0009` is live on EC2, nine verify checks passed.
`0010` is built, audited and verified — **not deployed yet.**

Everything below is sequenced. Do them in order; each one unblocks the next.

---

## DONE

- [x] Restored the 41 deleted files, recovered `develop`
- [x] Migrations `0002`–`0009` applied to RDS
- [x] Nine verify checks passing on your live database
- [x] Backend rebuilt, `/api/health` green, routes returning 401
- [x] `0010` built: JD attachments, mailer, group addresses, planner fix
- [x] `0010` audited — six bugs found and fixed, nothing of yours removed
- [x] GTM plan, messaging guide, build-vs-buy objection handler

---

## STEP 1 — Push the code (15 min)

On your Mac:

```bash
cd /Users/er.vishalmishra/Documents/GitHub/Cohort
git checkout develop && git pull origin develop
unzip -o ~/Downloads/cohort-0010.zip -d .

git add migrations/0010_attachments_and_mail.sql \
        backend/app/attachments.py backend/app/mailer.py \
        backend/app/routers/placement.py backend/app/routers/portal.py \
        frontend/app/app.html scripts/verify-deploy.sql docs/
git status --short
```

- [ ] `git status` shows **only** those paths
      → **never `git add -A`** after unzipping an overlay; that's what recorded
      the 41 deletions last time
- [ ] ```bash
      git commit -m "Add JD attachments, outbound mail, officer-set group addresses, planner navigation"
      git push origin develop
      ```
- [ ] **Turn on branch protection now, while you're on GitHub.**
      Settings → Branches → rule for `main` and `develop`: require a pull
      request, block force-push. Five minutes, and the next accidental mass
      delete becomes a diff you review instead of something that lands silently.

---

## STEP 2 — Set up SES (30 min, do before migrating)

Email is the thing `0010` adds. Without this configured, the migration applies
and then you stall at Step 4, because turning announcements on *is itself an
email*.

- [ ] SES console → **verify your sending domain**, with DKIM.
      (Verifying one address works, but domain + DKIM is what makes your
      announcements pass DMARC instead of landing in spam.)
- [ ] **Request production access** if you're still in the SES sandbox —
      otherwise it only delivers to addresses you've individually verified.
- [ ] SES → SMTP settings → **Create SMTP credentials**
- [ ] Append to `.env` on EC2:
      ```bash
      SMTP_HOST=email-smtp.ap-south-1.amazonaws.com
      SMTP_PORT=587
      SMTP_USER=<SES SMTP username>
      SMTP_PASSWORD=<SES SMTP password>
      SMTP_FROM=placements@yourdomain
      SMTP_FROM_NAME=Placement Cell
      SMTP_STARTTLS=true
      PORTAL_URL=http://15.252.205.151
      ```

Use SES rather than a Gmail app password: Gmail caps around 500 recipients a
day and will eventually flag an automated sender. SES SMTP credentials can only
send — they don't open a mailbox if they leak.

---

## STEP 3 — Migrate and rebuild (20 min)

```bash
cd ~/Cohort && git pull origin develop
set -a && source .env && set +a
./scripts/migrate-rds.sh
```

- [ ] `0010_attachments_and_mail` applies; `0002`–`0009` skip as already applied

```bash
psql "host=$RDS_HOST port=$RDS_PORT dbname=$RDS_DB user=$RDS_ADMIN_USER sslmode=require" \
     -P pager=off -f scripts/verify-deploy.sql
```

- [ ] Check 1 = **9** migrations, check 2 = **11** tables
- [ ] Check 11 says `INFO — not set` (expected; Step 4 fixes it)
- [ ] Any **FAIL** → stop, don't restart the app

```bash
cd ~/Cohort/infra
docker compose -f docker-compose.aws.yml up -d --build backend caddy
curl -s localhost/api/health
```

- [ ] `{"status":"ok","db":"up","schema":"current"}`
- [ ] New routes loaded (401 = exists + auth working; 404 = didn't load):
      ```bash
      curl -s -o /dev/null -w "attachments   %{http_code}\n" localhost/api/companies/1/attachments
      curl -s -o /dev/null -w "notify-groups %{http_code}\n" localhost/api/notify-groups
      ```

---

## STEP 4 — Turn on announcements (10 min)

- [ ] App → **Settings → Announcements** → **Set** the student group address
      (the Change button works now — it was `disabled` before, which is what
      you'd spotted)
- [ ] **Send confirmation**
- [ ] Open the link from that mailbox → tag flips to **confirmed**

Nothing emails until that tag says confirmed, and changing the address clears
it. Deliberate: an address verified months ago, when it was different, isn't
evidence about the address that's there now.

---

## STEP 5 — Walk the paths (20 min)

- [ ] Draft drive → **JD & files** → attach a JD → `2 slots left`
- [ ] Try a 4th → button disabled at 3
- [ ] **Publish** → drive opens **and** the group gets the JD by email
- [ ] Attach a JD *after* publishing → toast says it missed the announcement,
      **Resend** appears
- [ ] Student login → the JD downloads
- [ ] A *draft* drive's JD as a student → **404** (enforced server-side, not
      hidden in the UI)
- [ ] **Planner → Calendar** → arrows move between months
- [ ] ```bash
      psql "host=$RDS_HOST port=$RDS_PORT dbname=$RDS_DB user=$RDS_ADMIN_USER sslmode=require" \
        -P pager=off -c "SELECT to_address,subject,status,error,attachments,sent_at
                           FROM mail_log ORDER BY sent_at DESC LIMIT 10;"
      ```
      `sent` + `attachments=1` is the JD going out. `failed` puts the
      provider's reason in `error`.

---

## STEP 6 — Settle SSO (20 min)

The frontend is already built and dormant because `google_client_id` is empty.

```bash
cd ~/Cohort
grep -n "google\|id_token\|GOOGLE" backend/app/routers/auth_routes.py | head -20
curl -s -o /dev/null -w "%{http_code}\n" -X POST localhost/api/auth/google \
     -H 'Content-Type: application/json' -d '{"credential":"x"}'
```

- [ ] **401 / 400 / 422** → it exists. Google Cloud Console → Credentials →
      OAuth client ID (Web) → authorised origin `http://15.252.205.151` →
      `GOOGLE_CLIENT_ID=...` in `.env` → restart. Button appears automatically.
- [ ] **404** → never built. Send me `auth_routes.py` and I'll write it.
- [ ] **Check this in the grep:** does the callback match the Google email to an
      existing roster row and refuse if there's none? A Google account proves
      who someone is, not that they belong to your college. Without that, anyone
      with a Gmail address signs in.

---

## THEN — the product gaps

Ordered by how much each changes what Cohort can actually do.

- [ ] **Make `test-reminder` send.** It writes `notification_log` and stops —
      now the only route that does. Needs per-student sending, which means a
      queue, which is also the fix for SMTP-inside-the-transaction
      (`AUDIT_0010.md` §4). One job, not two half-jobs.

- [ ] **Blacklist with credits + absent tracking.** Build together. The biggest
      behavioural gap: Cohort currently has *no way to penalise a no-show*,
      which is the main lever a placement office has over students. Without it,
      an officer running a real season will keep a side spreadsheet — and a
      side spreadsheet is a drive that reverted to WhatsApp.

- [ ] **Accreditation export.** The commercial wedge — it moves the budget from
      the placement cell's discretionary spend to the institution's compliance
      budget, and changes who signs from the TPO to the Principal.
      **Validate before building:** get the NAAC/NBA/NIRF templates a real
      college used last cycle, confirm which fields come from placement data.
      Formats change between cycles; building against an assumption here is
      expensive.

- [ ] Internal staff remarks on a student (officer-only, never on the student's
      own profile route)
- [ ] Company job locations (distinct from `venue`, the interview room)
- [ ] Feedback reminder to placed students — cheap now that `notification_log`
      dedupes
- [ ] Remaining `SECURITY_REVIEW.md` findings, before a pilot college touches it

---

## IN PARALLEL — start selling

Don't wait for the product. Season runs Jul–Dec; colleges budget Feb–Jun. You
can't sell into a season already underway, so this one is for earning the right
to sell in February.

- [ ] **Line up 1–3 design partners.** Free or near-free, in exchange for real
      access. Sit in the office during an actual drive — don't ask what features
      they want, watch how they run it, note every copy-paste.
- [ ] **Run the free portal look** (`BUILD_VS_BUY.md` §3) as your way in.
      Thirty minutes, no charge. It's the credential: they can't evaluate a
      placement platform, but they can absolutely evaluate whether you found
      something real that nobody else spotted.
- [ ] **Validate the accreditation claim** with two or three real colleges
      before it becomes your primary pitch.
- [ ] Start posting on LinkedIn — voice and topics in
      `marketing-messaging-guide.md`.

**The gate before you scale anything:** one complete drive run end-to-end on
Cohort — publish through to offer recorded — with the officer *choosing* to use
it rather than being asked to. Don't hire, don't raise, don't push sales until
that has happened once.

---

## Reference

| Doc | For |
|---|---|
| `DEPLOY_0010.md` | Every command for this release, expected output, rollback |
| `AUDIT_0010.md` | The six bugs, how each was proven, what's left unfixed |
| `BUILD_VS_BUY.md` | "Why not build it ourselves?" + the free-audit play |
| `JSS_FEATURE_GAP.md` | Feature gaps worth closing |
| `GTM_ROLLOUT.md` | Accreditation wedge, staged rollout, pricing |
| `rollout-and-marketing-plan.md` | Full GTM with gates and kill criteria |
| `SECURITY_REVIEW.md` | Close before a pilot |

Migrations are additive — if the app misbehaves, roll the app back and leave the
schema alone (`DEPLOY_0010.md` §7).
