# Feature specification

Everything in the September 2026 brief: what each feature is, how it sits on the existing schema, what it costs in security, and how we'd know it works. Written against the real code on `develop`.

Read alongside [`ARCHITECTURE.md`](ARCHITECTURE.md) (structure), [`DOMAIN_MODEL.md`](DOMAIN_MODEL.md) (entities) and [`SECURITY_REVIEW.md`](SECURITY_REVIEW.md) (existing findings).

---

## 1. A correction to the earlier plan: email goes outward only

The previous revision proposed an inbound mailbox that turned forwarded company emails into draft drives. **That is removed.** The platform now sends email; it does not receive or parse it.

This is the right call, and not only because it was asked for. Inbound mail is untrusted input from outside the tenant, it needs sender verification, attachment scanning, parser hardening and a spoofing story, and it buys a convenience the officer can get by typing a company name in thirty seconds. Dropping it removes an entire attack surface for a small loss.

What remains is the useful half — **email as the outward channel for the broader pipeline**:

| Trigger | Goes to | Sent by |
|---|---|---|
| Drive published | Student group address | Automatic, on publish |
| Test reminder | Registered students only | **Officer presses send** |
| Placement recorded | The placed student | Automatic, reviewable |
| Feedback form reminder | The placed student | 3 days after the offer, once more after a week |
| Reminder due | The officer | Automatic at 9am |

---

## 2. Admin features

### 2.1 Calendar, notes, reminders

Three small features that share one section, because a placement officer thinks of them together.

**Calendar** is mostly derived, not entered: drive dates, test dates and last dates already exist as `companies.deadline` and `company_notes.note_date`. The table `company_notes` already carries `kind` (`visit | test | deadline | note`), which *is* a calendar event. So the calendar is a view over existing data plus manual events.

**Notes** — `company_notes` again, with `company_id` nullable for a general note. Already built.

**Reminders** — genuinely new, and deliberately private to the person who set them.

```sql
CREATE TABLE reminders (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  college_id bigint NOT NULL REFERENCES colleges(id) ON DELETE CASCADE,
  user_id    bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title text NOT NULL, body text,
  due_at timestamptz NOT NULL,
  repeat_rule text,                  -- null | 'weekly' | 'monthly'
  related_type text, related_id bigint,
  done_at timestamptz, notified_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);
```

RLS: `college_id = app_college() AND user_id = app_user()`. A reminder is a private note to self — **not** visible to other staff, and never to CRs or students. Getting this wrong would leak "call HR about the Meridian mess" to a student rep.

### 2.2 Consolidated drives tab

One screen, search plus filters on status, bucket, branch and date, with the whole pipeline visible per row. Search covers company name, role and bucket alias. Filters compose (`bucket=Tier 2` AND `closing this week`) and live in the query string so a filtered view can be bookmarked and shared with a colleague.

Needs pagination from the start — 40 drives a year becomes 200 in five years, and `SECURITY_REVIEW.md` F-4 is already a live example of what silent truncation does.

### 2.3 Registration sheet download, with configurable columns

Two presets — **short info** (roll, name, branch, email, CGPA) and **full info** — plus a column picker the placement cell configures once and saves.

```sql
CREATE TABLE export_templates (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  college_id bigint NOT NULL REFERENCES colleges(id) ON DELETE CASCADE,
  name text NOT NULL,
  columns jsonb NOT NULL,            -- ordered array of column keys
  is_default boolean NOT NULL DEFAULT false,
  created_by bigint REFERENCES users(id) ON DELETE SET NULL
);
```

**The security-critical detail:** `columns` is validated against a **server-side allow-list**, never used to build SQL. A client that posts `["password_hash"]` or `["cgpa) --"]` gets a 422. The allow-list maps a key to an expression (`roll_no` → `s.roll_no`, `tenth_pct` → `s.attributes->>'tenth_pct'`); anything not in the map does not exist. This is the single most likely place for this feature set to grow an injection or an over-exposure bug, because "let the user choose columns" reads as harmless.

Also: exporting is a **capability** (`export_registrations`), officer-grantable, and every export writes an `audit_log` row with the drive, the template, the column list and the row count.

### 2.4 Resume bundles

Download every resume for a drive as a zip, foldered as `<Company>_<test date>/`, one PDF per student named by roll number, with a `missing.txt` listing registrants who have no resume.

This is the highest-risk feature in the brief — it is a **bulk PII export in one click** — so it comes with conditions:

- **Officer-only** capability, never CR-grantable.
- **Scoped to registrants of that drive.** Never "all students". A company sees resumes of people who chose to apply to that company, and nobody else.
- **Generated asynchronously and streamed.** Building a 200-PDF zip in request memory will take the API process down. A job writes to object storage and returns a short-lived signed link.
- **Audited**, with the count, and rate-limited per user per hour.
- **Filename sanitisation.** The folder name comes from a company name typed by a human. `../../etc` and a 300-character name are both real inputs. Slugify, cap length, never interpolate into a shell.
- This makes **ADR-06 (resumes to object storage) urgent** rather than eventual — zipping bytea out of Postgres for 200 students is a memory and I/O problem you feel on the first real drive.

### 2.5 Announce on publish, to a configurable group

The address is per-college configuration, not hardcoded:

```sql
ALTER TABLE colleges ADD COLUMN notify_groups jsonb NOT NULL DEFAULT '{}';
-- {"students":"placements-2027@demo.ac.in","juniors":"students-all@demo.ac.in"}
```

Two rules that matter more than the feature:

**The address must be verified before use.** An admin who can set an arbitrary destination can point every announcement at an address outside the college. Send a confirmation link to the address; require the domain to match the college's `email_domain` (already on the `colleges` table) or an explicitly approved alternate.

**Group emails carry no personal data.** A group list is wider than whoever set it up believes — alumni linger, forwards happen. The announcement says a drive is open and links to the portal; it never contains names, marks or contact details. Anything personal goes to the individual student, addressed to them.

Announcement fires on **publish**, not on save. Adding a company is bookkeeping; publishing is the decision. That distinction is already the right one for audit and it's the right one here.

### 2.6 Test reminder, triggered by the officer

To registered students only, and only when the officer presses the button — the system will not decide when a reminder is appropriate.

**Idempotency is the whole design.** A double click, a retried request or a reconnecting client must not send twice. The send is keyed on `(drive_id, kind, date)` with a unique constraint; the second attempt finds the row and does nothing. Same mechanism the existing `notifications` table already uses for escalations, where `UNIQUE (college_id, recipient_role, kind, resource_type, resource_id)` makes a double escalation harmless. Reuse that pattern rather than inventing one.

Sending happens through a queue, not inside the HTTP request. 200 emails inline is a timeout.

### 2.7 Congratulations and the feedback form

Recording an offer triggers a congratulations email and, three days later, a feedback reminder.

**The feedback form already exists in the schema** — `feedback(student_id, company_id, role, ctc, rounds, difficulty 1–5, topics, tips)`, with `POST /api/me/feedback` and `GET /api/me/feedback` already implemented in `portal.py`. What's missing is only the trigger and the pre-population: the form opens with company, role and CTC already filled from the offer record, so the student writes the review and rates difficulty, nothing else.

The review is written **in the portal**, not in the email. An email link that posts content is a bearer credential sitting in an inbox.

Two considerations, since reviews are user-generated content shown to the whole college and later to juniors: escape on render (the existing `errors.py` discipline shows this team already thinks about output safety), and let the writer choose whether their name appears — an honest review of a difficult interview is easier to write when it isn't attributed.

### 2.8 Buckets with aliases, and company-specific rules

Every college names its tiers differently. Make the names data:

```sql
CREATE TABLE buckets (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  college_id bigint NOT NULL REFERENCES colleges(id) ON DELETE CASCADE,
  key text NOT NULL,                 -- stable: 'tier1'
  label text NOT NULL,               -- shown: 'Tier 1'
  aliases text[] NOT NULL DEFAULT '{}',  -- 'Super Dream', 'A+'
  min_package numeric, max_package numeric,
  counts_toward_cap boolean NOT NULL DEFAULT true,
  ignores_cap boolean NOT NULL DEFAULT false,
  sort_order int NOT NULL DEFAULT 0,
  UNIQUE (college_id, key)
);
```

`companies.category` keeps its current text value and starts referencing `buckets.key`, so nothing breaks. The offer-cap behaviour moves out of `placement_policy` free-text into per-bucket flags the existing `check_policy()` engine can read directly.

**Company-specific criteria, including gender-restricted drives.** The eligibility engine already handles this without change — rules are a JSON tree over student attributes, so `{"field":"gender","op":"==","value":"female"}` works the moment `gender` is a defined attribute in `attribute_defs`. Nothing new is needed in the evaluator.

What *is* needed is handling around it. Gender-restricted hiring is legitimate in India as diversity recruitment and is common at exactly the companies a placement cell wants — but it is also the kind of rule that causes damage when set carelessly or unexplained. So: the restriction is recorded against the company with **who set it and the stated reason**, it is written to `audit_log`, and — importantly — the student sees it as a plain reason rather than a silent absence: *"This drive is open to women candidates only."* A student who can't apply and isn't told why assumes the system is broken or that someone made a mistake about them. The same applies to any company-specific restriction.

### 2.9 Analytics

Five views rather than one page: overview with offers-by-month, by branch (with a branch × bucket heatmap), stage drop-off, salary bands, and the accreditation exports.

Two things worth stating because they're easy to get wrong. **Median, not mean** — eight offers above 20 lakh drag a mean upward and produce a number management will quote and later have to defend. Show both, lead with the median. And **every chart is one measure on one scale**; where two measures matter (offers and median package by branch), they sit side by side as a number, not as a second axis.

All of it derives from `applications`, `round_progress` and `offers`, so the dashboard and the NAAC submission are computed from the same rows and cannot disagree. The drop-off view depends on `round_progress` actually being written — currently it is not (`DOMAIN_MODEL.md` §3), which is the one real blocker in this list.

### 2.10 Pro features

Locked capabilities the college unlocks, shown with an asterisk: partner data sharing, pool placements, test sessions, cohorts, events, weekly/monthly tests, articles.

```sql
CREATE TABLE entitlements (
  college_id bigint NOT NULL REFERENCES colleges(id) ON DELETE CASCADE,
  feature text NOT NULL,
  enabled boolean NOT NULL DEFAULT false,
  enabled_at timestamptz, enabled_by bigint REFERENCES users(id) ON DELETE SET NULL,
  PRIMARY KEY (college_id, feature)
);
```

**Entitlements are not permissions.** A permission answers "may this person do it"; an entitlement answers "has this college bought it". Keep them separate, check both, and enforce both **server-side**. A Pro feature that is only hidden in the UI is not locked — it is `SECURITY_REVIEW.md` F-9 with a price tag.

And the rule that matters most: **an entitlement never overrides a student's consent.** A college turning on "share student data with partners" grants the right to *ask*; each student still decides individually and can withdraw. If those two ever collapse into one switch, the product has sold something that wasn't the college's to sell.

---

## 3. CR and junior model

### 3.1 CRs

Added by the officer, who sets branch coverage (one or several) and access level. Each CR gets a login code, shown **once**.

The code is a credential, so it follows the fix already recommended for student activation codes in F-3: **hashed at rest, expiring, single-use, reissued rather than recovered, and every issue and use audited**. The mockup says "lost codes are reissued, never recovered", which is the correct and honest behaviour to build.

Multi-branch coverage needs a small change: `memberships.branch_id` is a single column today. Either allow several membership rows per user (cleanest, works with existing RLS) or add `branch_ids bigint[]`. The first is preferable — the RLS policies already key off `app_branch()`, and multiple memberships keeps one code path.

Capabilities extend the existing `permissions.py` catalogue, with `import_junior_roster` added and `view_activation_codes` still off by default. The ungrantable set grows by one: `manage_pro`.

### 3.2 Juniors

A junior is **not a new role.** They are a `student` in a non-final year — same identity, same RLS, different visibility. Adding a fourth role would duplicate every policy in the schema for a difference that is one column:

```sql
ALTER TABLE students ADD COLUMN batch_year int;      -- graduating year
ALTER TABLE students ADD COLUMN program_years int DEFAULT 4;
```

Final-year is derived. Drives are visible to final-year students; interview experiences are visible to everyone. That is a `WHERE` clause, not a role.

**On the "unified code" for juniors:** a single shared code will be outside the branch within a day, and outside the college within a week — group chats are efficient. The mockup therefore issues **one code per student**, valid 30 days, single-use. It costs nothing more (the import already produces a row per student, exactly as the existing roster import does) and it means a leaked code compromises one account instead of a batch. If a shared code is ever genuinely needed, it should unlock only non-personal content and never create a session.

Roster import by CRs is branch-scoped by RLS and capability-gated, with a dry-run preview showing what will change before anything is written — the same preview recommended for the officer's roster import in `USE_CASES.md` §3.4, and for the same reason: the first import is where the data is messiest.

---

## 4. Student side

**Eligible and ineligible are separated**, and ineligible drives are hidden unless the student asks. Seeing eight drives you can't apply to, every visit, is discouraging and useless. But when shown, each carries the specific reason — the rule engine already produces these strings, and they are the product's sharpest feature.

**Filters** on bucket, package and closing date, because a student with 40 open drives has the same scanning problem the officer does.

**Premium** — resume review, 1:1 mentorship, pool campus apply, coding test practice — sits behind the same entitlement mechanism, checked server-side.

One line in the mockup is a product commitment worth keeping: *"Premium never changes who can apply to a drive, and never moves you up a shortlist."* The moment money affects eligibility or ranking, the platform is selling access to placements, and every college's trust in it is gone. Premium buys preparation, not advantage.

---

## 5. Capability checklist

Campus hiring platforms are an established category with incumbents at significant scale — Superset being the most prominent in India. **Verify the current competitor feature set directly before using any of this in a pitch**; this is a checklist of capability areas, not a claim about any specific product's roadmap.

| Area | Status here |
|---|---|
| Roster import, validation, student onboarding | Built; needs dry-run preview and pagination |
| Configurable eligibility rules | **Built and strong** — data-driven, with human-readable failure reasons |
| Placement policy (caps, slabs, upgrades) | Built |
| Drive lifecycle, rounds, shortlisting | Partly — needs round history and bulk actions |
| Registration exports, configurable columns | Specified here |
| Resume collection and bundling | Resumes built; bundling specified here |
| Notifications and reminders | Specified here |
| Analytics and accreditation reporting | Analytics built; accreditation exports are the gap and the commercial unlock |
| Interview experience knowledge base | **Built** — and rarely present elsewhere |
| Multi-tenant isolation | **Built, and strong** — RLS with FORCE, non-superuser role |
| Delegated CR access with a hard ceiling | **Built** — unusual, and specific to how Indian colleges actually run placements |
| Assessments / proctored tests | Not built — Pro, later, correctly |
| Cross-college talent discovery | Not built — Phase 2, correctly |
| Employer-side console | Not built |
| SSO, MFA, SOC 2 / ISO posture | Google SSO built; the rest is a gap that matters when selling to larger institutions |

The honest read: **on the college-operations half this is competitive, and on two things — explainable eligibility and the CR hierarchy — it is ahead.** The gaps are the employer side and enterprise security paperwork. Since the strategy in `GTM_ROLLOUT.md` is to win Tier-2/3 colleges on operations first, that is the right shape of gap to have.

---

## 6. System design principles

Six rules the new features should be reviewed against.

**Single source of truth.** A number shown on a dashboard, in an export and in a NAAC submission comes from the same query. Derived caches (`applications.current_round`, `students.cohort_score`, the consent boolean) are written in the same transaction as the fact they summarise, and never edited independently.

**Side effects are idempotent.** Every email, every export, every bulk update carries a key that makes the second attempt a no-op. Assume every request will be retried, because eventually one will be.

**Fail closed.** A missing capability, an unverified group address, an unknown export column and an expired code all deny. The existing schema-version middleware — which 503s the API rather than serving against a half-migrated database — is exactly this instinct, already present in the codebase.

**Least privilege, structurally.** Officer-only capabilities are not "unchecked by default", they are unrepresentable in a CR grant. Entitlements and permissions are separate checks. RLS remains an independent layer that would still hold if every application check were removed.

**Data minimisation.** Group emails carry no personal data. Exports carry the columns chosen, not everything. Juniors see experiences, not rosters. Companies see registrants, not the college.

**Heavy work is asynchronous.** Zip building and bulk email run as jobs with status, not inside a request. A placement officer clicking "download 200 resumes" should not be able to take the API down for everyone else.

---

## 7. What to measure

**System**

| Metric | Target |
|---|---|
| API p95 latency, read paths | < 300 ms |
| Eligibility sweep for one drive over the roster | < 800 ms |
| Export job completion | < 60 s for 200 resumes |
| Email delivery rate | > 98%, bounces surfaced to the officer |
| Duplicate sends | Zero — measured, not assumed |
| 5xx rate | < 0.1%, every one traceable to a request id |
| Cross-tenant leak tests | Passing on every table, every build |

**Product**

| Metric | Why |
|---|---|
| Drives run end to end on the platform | The real adoption signal |
| Eligibility disputes per drive | Should trend to zero — the explainability feature working |
| Time from company added to drive published | Officer friction |
| Feedback form completion rate | Whether the knowledge base compounds |
| Junior code activation rate | Whether next year's cohort arrives ready |
| Export used before an accreditation deadline | The strongest renewal predictor |
| Consent opt-in rate, asked honestly | The Phase 2 go/no-go |

---

## 8. Build order

**First — unblocks everything else.** Write `round_progress` with actor and timestamp; the F-1/F-2/F-3 security fixes; resumes to object storage.

**Then — the daily surface.** Consolidated drives with search and filters, bulk round updates, registration exports with the column allow-list, resume bundles as async jobs.

**Then — the outward channel.** Verified group addresses, publish announcements, officer-triggered test reminders, congratulations and feedback triggers, reminders.

**Then — the rest.** Buckets with aliases, calendar and notes, the five analytics views, accreditation exports, CR codes and multi-branch coverage, junior import.

**Last, and gated.** Entitlements and the Pro/Premium surfaces. Build the mechanism early enough that features can be gated properly; build the features themselves only when a college has asked and paid.
