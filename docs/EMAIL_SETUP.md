# Email setup (Amazon SES, ap-south-1)

How to make drive announcements actually send. Written against the code as it
stands — `backend/app/mailer.py` and `publish_drive` in
`backend/app/routers/placement.py` — not against a generic SES tutorial.

Researched 29 September 2026. Where AWS has changed something recently, or
where I could not verify a figure, it is flagged inline rather than asserted.

---

## What this system actually sends

Worth being precise about, because it decides most of the setup.

On `POST /api/companies/{id}/publish`, if the college has a **verified student
group address** (`colleges.notify_groups -> 'students'`, with a non-null
`verified_at`), the backend sends **one message** to that one address, with the
JD files attached. Not one message per student. A college with 400 students in
`cse2027@college.ac.in` is a single SES send.

Consequences, in order of how much they matter:

1. **Volume is tiny.** Ten colleges running twenty drives a year is 200 sends a
   year. Cost is effectively zero. Sending quota will never be the constraint.
2. **Complaint rate is the real risk, not volume.** SES suspends on *rates*,
   not counts: account under review at 0.1% complaints, sending paused at 0.5%.
   One send reaching 400 inboxes still counts as **one** send in the
   denominator. A single student hitting "Report spam" on a month with 30 sends
   is 3.3% — six times the pause threshold. This is the failure mode to design
   against, and everything below about From names and unsubscribe text is
   aimed at it.
3. **Every recipient is a college-controlled address that a human verified
   first.** That is a genuine double opt-in and it is the strongest sentence in
   your production-access request. Say it explicitly.

---

## Two things in the code to know before you start

### 1. The From address is global, not per-college

`mailer.send_mail` reads `SMTP_FROM` and `SMTP_FROM_NAME` from the environment.
There is no per-college sender column — I checked every migration. So every
college's announcements go out as the same address with the same display name.

The module docstring says the message "is sent as the college's own configured
address." **That is not what the code does.** The docstring is describing an
intention, not the implementation.

Keep the global sender. It is the correct call: to send as `placements@gvit.ac.in`
you would need GVIT's IT department to add your SES to their SPF and publish
your DKIM records in their zone, which is weeks of email for every college you
onboard, and a DMARC failure for every one that hasn't done it yet. One domain
you control, verified once, is right.

But fix the display name. Right now a GVIT student sees:

    From: Placement Cell <placements@tracecampus.in>

on mail about their own college, from a domain they have never heard of. That
is the complaint in point 2 above, waiting to happen. The college name is
already loaded in `publish_drive` and passed into `drive_announcement`, so it
is available at the send site — it just isn't reaching the From header. Making
it read

    From: GVIT Placement Cell <placements@tracecampus.in>

is a small change to `send_mail` (a `from_name` parameter) plus one line at the
call site. **Not done yet** — flagged here so it is a decision, not an
oversight.

### 2. Bounces and complaints don't come back into the database

`mail_log` records what *your server handed to SES*, which is not the same as
what arrived. SES auto-suppresses hard bounces and complaints at the account
level, which means it will silently stop delivering to a dead group address
while `mail_log` keeps saying `sent` and the officer keeps seeing "Announced".

You attest on the production-access form that you handle this. Section 6 below
sets up the SNS side; wiring it back into the database is a follow-up task, not
a blocker for launch.

---

## The setup, in order

Do all of it in **ap-south-1 (Mumbai)**. Identity verification, DKIM, sandbox
status, quotas, SMTP credentials and the suppression list are every one of them
per-region. Creating an identity in whatever region the console happened to
open on is the single most common wasted afternoon with SES. Check the region
selector before each step.

### 1. Verify the sending domain

SES console → **Configuration → Identities → Create identity → Domain**.

Enter the apex domain — `tracecampus.in`, not `www.tracecampus.in`. Leave
**Easy DKIM / RSA 2048**. Tick **Use a custom MAIL FROM domain** and enter
`mail.tracecampus.in`; set **Behavior on MX failure** to **Use default MAIL
FROM domain**, so a DNS mistake degrades to a missing SPF alignment rather than
hard-failing every send.

Do not pick **Deterministic Easy DKIM (DEED)** — it is for multi-region sending
and you do not need it.

Note: domain verification is no longer a separate `_amazonses` TXT token. SES
now verifies ownership through the DKIM CNAMEs themselves. Guides that tell you
to add a TXT verification record are out of date.

### 2. Publish DNS

Five records. Three for DKIM (SES gives you the tokens — copy them from the
identity's Authentication tab, or Download .csv):

    CNAME  <token1>._domainkey.tracecampus.in  →  <token1>.dkim.ap-south-1.amazonses.com
    CNAME  <token2>._domainkey.tracecampus.in  →  <token2>.dkim.ap-south-1.amazonses.com
    CNAME  <token3>._domainkey.tracecampus.in  →  <token3>.dkim.ap-south-1.amazonses.com

Two for the custom MAIL FROM:

    MX   mail.tracecampus.in  →  10 feedback-smtp.ap-south-1.amazonses.com
    TXT  mail.tracecampus.in  →  "v=spf1 include:amazonses.com ~all"

**Exactly one MX record on that subdomain.** More than one and custom MAIL FROM
fails outright.

**The region must be `ap-south-1` in both the DKIM values and the MX.** Copying
`feedback-smtp.us-east-1.amazonaws.com` from a blog post fails silently: with
"use default on MX failure" set, mail keeps flowing and you simply lose SPF
alignment without any error anywhere.

Two DNS-panel traps: the token name has **no leading underscore before the
token** (`abc123._domainkey`, not `_abc123._domainkey`), and many panels
auto-append the zone — if yours does, enter only `<token>._domainkey` as the
host or you will end up with `...tracecampus.in.tracecampus.in`.

Check your own work before sitting around waiting:

    dig +short CNAME <token1>._domainkey.tracecampus.in
    dig +short MX mail.tracecampus.in
    dig +short TXT mail.tracecampus.in

AWS documents up to 72 hours. In practice it is usually 5–30 minutes. The
identity flips to **Verified** and DKIM shows **Successful**.

### 3. Publish DMARC

    TXT  _dmarc.tracecampus.in  →  "v=DMARC1; p=none; rua=mailto:dmarc@tracecampus.in"

At your volume DMARC is not strictly required by Gmail — their hard
requirements kick in at 5,000 messages a day to personal Gmail addresses.
Publish it anyway: it is one record, it stops anyone spoofing the domain, and
the `rua` reports are the only way you will find out your mail is failing
somewhere.

**Stay at `p=none` for now.** Do not jump to `p=reject`. College group
addresses are usually mailing lists, and lists break authentication two ways:
forwarding breaks SPF (the forwarding hop isn't in your SPF record), and any
list that prepends `[CSE-2027]` to the subject or appends a footer invalidates
your DKIM signature. With both legs broken, `p=reject` instructs the receiving
server to bounce *your own legitimate mail*. Move to `quarantine` only once the
`rua` reports show what the colleges' lists are actually doing to your messages.

One more: if `tracecampus.in` already sends through Google Workspace, you need
**one merged SPF record**, not two. Two SPF TXT records on the same name is a
permerror and fails SPF completely.

### 4. Generate SMTP credentials

SES console → **SMTP settings → Create SMTP credentials** → accept the IAM user
name → **Create user** → **Show** the password → **Download .csv**.

**These are not AWS access keys.** The SMTP password is derived from an IAM
secret by a region-salted HMAC; pasting an IAM secret access key into
`SMTP_PASSWORD` will never authenticate. They are also **region-specific** — a
password minted for ap-south-1 will not work against any other region's
endpoint.

**The password is shown exactly once.** If you close that dialog without
downloading, you delete the IAM user and start over.

Endpoint for your `.env`:

    SMTP_HOST=email-smtp.ap-south-1.amazonaws.com
    SMTP_PORT=587
    SMTP_STARTTLS=true

Port 587 with STARTTLS is the right choice. 2587 is the fallback if something
blocks 587. Avoid port 25 — EC2 throttles it by default and ISPs block it.

Connectivity check from the EC2 box:

    openssl s_client -starttls smtp -crlf -connect email-smtp.ap-south-1.amazonaws.com:587

### 5. Test while still in the sandbox

Sandbox limits: **200 emails per 24 hours, 1 per second, and every recipient
address must itself be verified in SES.** They cannot be raised.

That last one matters: you **cannot** test against a real college group address
while in the sandbox without someone at that college clicking a verification
link. Verify one of your own addresses, set it as a test college's
`notify_groups.students.email`, and publish a drive against it.

### 6. Set up a configuration set (do this before production access)

Not required to send, but it is how bounce and complaint events reach you, and
you are about to attest that you handle them.

Create a configuration set with an SNS event destination for `BOUNCE`,
`COMPLAINT`, `DELIVERY` and `REJECT`, then set it as the **default
configuration set** on the domain identity so every send is tracked without the
application doing anything.

SES also has a **tenants** feature aimed at exactly this product shape —
per-tenant reputation isolation, so one college's bad list doesn't hide behind
another's good one. Worth looking at once there are several colleges live; not
needed on day one.

### 7. Request production access

SES console → **Account dashboard** → **Request production access**.

Mail type: **Transactional**. The free-text use case is the only part that is
actually read. Vague descriptions get a follow-up question that costs days.
Something close to this, adjusted to the truth at the time you send it:

> TRACE Campus is a placement-management platform used by engineering colleges
> in India. We send transactional notifications — placement drive
> announcements with job descriptions attached — to the official placement
> group address of each college. That address is configured by the college's
> own Placement Officer and must be confirmed through a verification email
> before the system will send anything to it; unverified addresses are skipped
> in code. There is no purchased, rented or scraped list, and no address is
> ever added by us. Expected volume is approximately 200–400 emails per year
> initially. We send from tracecampus.in, which is domain-verified with Easy
> DKIM, a custom MAIL FROM at mail.tracecampus.in, and DMARC published.
> Bounce and complaint events are delivered via SNS on an SES configuration
> set. Every message identifies the college's placement cell and carries an
> unsubscribe path back to that college's placement officer.

Do not send that last sentence until it is true.

AWS documents a response within 24 hours. Realistically most clean requests
clear inside a day; anything that triggers a follow-up adds a few days per
round trip. **Start this early** — it is the longest lead time in the whole
setup, and nothing reaches a real college address until it clears.

### 8. Fill in `.env` on EC2 and recreate the backend

    SMTP_HOST=email-smtp.ap-south-1.amazonaws.com
    SMTP_PORT=587
    SMTP_USER=<from the .csv>
    SMTP_PASSWORD=<from the .csv>
    SMTP_FROM=placements@tracecampus.in
    SMTP_FROM_NAME=Placement Cell
    SMTP_STARTTLS=true
    SMTP_TIMEOUT=20
    PORTAL_URL=https://placements.yourdomain.in

`SMTP_FROM` must be on the verified domain. `PORTAL_URL` must be the
public URL this deployment answers on, with no trailing slash — the
group-verification email builds its confirm link from it, and an empty
value produces a link nobody can click, which means the group address
never verifies and announcements are skipped in silence. Then:

    cd ~/Cohort/infra
    docker compose -f docker-compose.aws.yml up -d --force-recreate backend

No rebuild needed — these are environment variables, not code.

With `SMTP_HOST` empty the app still starts and publishing a drive still
succeeds, with the announcement skipped and `mail_status` reporting why. That
is deliberate: a college that hasn't set up email yet should not get a 500 when
they publish.

---

## Cost

Negligible at this volume — a few hundred emails a year is cents. Note that AWS
changed SES pricing in July 2026, introducing named plans alongside the old
pay-per-use model, and the old "62,000 free emails a month from EC2" tier no
longer appears in current documentation. **Check Account dashboard → pricing
plan after signup** and confirm you are not defaulted onto something with a
monthly fee. At your volume the per-email difference between plans is
irrelevant; a fixed monthly charge is not.

---

## What will go wrong

1. **Wrong region.** Everything in SES is per-region. Verify, mint credentials
   and exit the sandbox in ap-south-1 or none of it counts.
2. **IAM secret key pasted as `SMTP_PASSWORD`.** Different string entirely. Use
   the .csv from SMTP settings.
3. **SMTP credentials not downloaded.** Shown once. Delete the IAM user and
   redo.
4. **DKIM CNAME mangled** by the DNS panel — extra underscore, or zone appended
   twice. `dig` before you wait.
5. **MAIL FROM MX copied from a US-region tutorial.** Silent failure; SPF
   alignment quietly gone.
6. **Two SPF records on one name.** Permerror, SPF fails completely.
7. **Testing against a real college group address in the sandbox.** Needs
   someone at that college to click a link. Use your own address.
8. **One spam complaint.** At your volume this is the highest-probability
   serious failure in the whole setup. It is why the From display name matters.
9. **`p=reject` too early.** College mailing lists will break your DKIM
   signature and DMARC will then tell receivers to bounce your own mail.
10. **Suppression list swallowing sends silently.** `mail_log` says `sent`; SES
    dropped it. Until the SNS feedback loop is wired into the database, treat
    `mail_log` as "handed to SES", not "delivered".

---

## Still to do after this

- Pass the college name into the From display name (section "Two things in the
  code", item 1).
- Consume SNS bounce/complaint events and reflect them in `mail_log` and the
  officer's view, so "Announced" means delivered.
- An unsubscribe path. Not legally forced at this volume, but it is the
  difference between a student clicking "unsubscribe" and clicking "spam", and
  only one of those can suspend the account.
