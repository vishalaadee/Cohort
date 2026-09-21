# UI/UX notes

`ui-redesign.html` is a working mockup — one file, static data, no backend. The top bar switches between the four roles and between dark and light.

---

## 1. Colour: one accent per role

House-style pairings on black, so a screenshot tells you whose screen it is before you read a word.

| Role | Dark | Light |
|---|---|---|
| Admin | crimson `#D9463F` | `#B3261E` |
| CR | green `#33B36B` | `#1E7A46` |
| Student | gold `#D4A937` | `#8A6A12` |
| Junior | deep blue `#4483DD` | `#1F4FA0` |

Neutrals are shared across all four — only `--acc`, `--acc-hi`, `--acc-soft` and `--acc-ink` change, driven by `data-role` on the root element, so this costs four short CSS blocks rather than four themes.

Status colours stay **constant** across roles: green for good, amber for attention, red for a problem, gold for Pro. If status followed the role accent, "needs attention" on the admin screen would be indistinguishable from the brand, which is how a red interface stops communicating urgency.

Dark is the default. Light is a full second palette, not an inversion.

---

## 2. Structure: tabs, so features have somewhere to go

Nothing is hidden by deletion. Sections that carry a lot use tabs, and each tab holds one job:

| Section | Tabs |
|---|---|
| Planner | Calendar · Notes · Reminders |
| A drive | Students · Downloads · Details · Emails · Feedback |
| Companies | All companies · Adding a company · Buckets |
| Analytics | Overview · By branch · Drop-off · Salary · NAAC/NBA/NIRF |
| Settings | Notifications · CRs and access · Placement policy · Pro |
| CR | To do · Questions · Students |

The useful property is that adding the next feature costs one tab, not one more thing crowding an existing screen.

**Admin nav:** Today · Planner · Drives · Companies · Students · Analytics · Settings.
**CR:** My branch · Juniors · Experiences. **Student:** Home · Drives · Experiences · My details · Premium. **Junior:** Home · Experiences · Prepare.

---

## 3. The screens that carry the new work

**Today** leads with what's blocking, then reminders due, then numbers. Publishing, sending a test reminder and reviewing a queued congratulations email all start here.

**Planner** — the calendar is mostly *derived*: drive dates, test dates and last dates already exist as data, so they appear without anyone entering them. Notes map to the existing `company_notes` table. Reminders are new and private to the person who set them.

**Drives** — search plus filters on status, bucket and branch, with the whole pipeline on each row as a labelled strip (`31 24 16 9 4 1` under a legend row, so it reads as stages rather than a code). Amber means that round hasn't moved in five days. Bulk select drives to send a test reminder, extend, or close.

**A drive → Downloads** is the registration sheet with a column picker, Short info / Full info presets, a saveable preset, and the resume bundle — a zip foldered `Nova-Analytics_2026-09-19`, one PDF per student named by roll number, with a `missing.txt` for registrants who have no resume.

**A drive → Emails** shows what has been sent and what is queued, with the test reminder as an explicit button. Nothing about inbound mail: the platform sends, it does not receive.

**Companies → Buckets** is where Tier 1 / Tier 2 / Dream / Core get their criteria *and their aliases*, because every college calls these something different and should see its own words.

**Adding a company** includes the company-specific restriction field — a women-only diversity drive, for instance — recorded with who set it and why, and shown to students as a plain reason rather than a silent absence.

**Analytics** is five views: offers by month, placed by branch with a branch × bucket heatmap, stage drop-off, salary bands, and the accreditation exports.

**Settings → Pro** is the entitlement surface: seven locked features with an asterisk. The note under it is a product commitment, not decoration — turning a Pro feature on never overrides a student's own consent.

**Student → Drives** separates what you can apply to from what you can't, hides the second list unless asked, and gives each blocked drive its specific reason. **Student → Premium** is locked features with the line that matters: premium never changes eligibility and never moves anyone up a shortlist.

**CR → Juniors** is roster import with a dry-run preview, and per-student sign-in codes. **Junior** sees interview experiences and preparation material — no drives, no rosters, no other students' marks.

---

## 4. Two design decisions worth defending

**One code per junior, not a shared one.** A single code circulated to a batch is outside the branch in a day. Per-student codes cost nothing extra — the import already creates a row per student — and a leak then compromises one account rather than a year group.

**Buttons that cause something irreversible say what happens.** "Send test reminder" goes to 28 registered students; the screen says so before the click, and says a reminder already sent today can't be sent twice by accident.

---

## 5. Porting it

1. **Tokens and the role accent** — four small CSS blocks plus `data-role` on the root. Everything else inherits.
2. **Tabs** — a tiny component; `Shell()` and the hash router in `app.html` stay as they are.
3. **The drives list with the stage strip** — needs stage counts, a `GROUP BY` over `round_progress` once it's actually being written (`docs/DOMAIN_MODEL.md` §3). This is the one real blocker.
4. **Downloads** — the column allow-list is server-side (`docs/FEATURE_SPEC.md` §2.3); resume bundles are async jobs, not request-time work.
5. **Emails** — verified group addresses and idempotent sends (§2.5, §2.6). Infrastructure, not UI.
6. **Entitlements last** — build the gate early, the features behind it late.

---

## 6. Deliberately not there

No drag and drop, no animation, no icon set, no onboarding tour, no dashboard customisation. A drive board is pleasant for one drive and unusable for forty; a table with bulk actions does the same job in one click, works on a phone, and leaves the same audit trail.
