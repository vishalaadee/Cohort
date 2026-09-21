# Security and correctness review

Findings from reading the code on `develop` in September 2026. Every finding cites the file it came from. Nothing here is theoretical or copied from a checklist — where something needs verification on a running database before it can be called a vulnerability, that is stated, with the query to run.

**Overall assessment:** the security foundation is better than most projects at this stage. Double-enforced tenant isolation with `FORCE ROW LEVEL SECURITY`, a non-superuser application role, transaction-local GUCs that cannot leak across a pooled connection, bcrypt at cost 12, uniform error envelopes that don't leak internals, rate-limited auth endpoints, and login errors that deliberately don't reveal which credential component matched. That is a deliberate, competent baseline. The findings below are specific gaps, not a verdict on the whole.

Severity: **High** = could expose data across a tenant boundary or allow impersonation. **Medium** = data exposure within a tenant, or a control that fails silently. **Low** = hardening.

---

## F-1 — `recruiter_candidates` view may bypass Row-Level Security · High · *verify first*

**Where:** `migrations/0005_consent_score.sql`

```sql
CREATE OR REPLACE VIEW recruiter_candidates AS
  SELECT s.id, s.full_name, s.email, b.code AS branch, s.cgpa, ...
  FROM students s JOIN branches b ... JOIN colleges c ...
  WHERE s.consent_recruiter_share = true AND s.cohort_score IS NOT NULL;
-- No RLS on the view — it's meant for the future recruiter portal.
```

**The mechanic.** In PostgreSQL, a view accesses its underlying tables with the **view owner's** privileges, and unless the view is created with `security_invoker = true` (PostgreSQL 15+), row-level security is evaluated against the *view owner*, not the caller. `FORCE ROW LEVEL SECURITY` keeps a normal table owner subject to policy — but a role holding the `BYPASSRLS` attribute (a superuser, notably) is exempt regardless of `FORCE`.

**Why it matters here.** The view is created by whichever role applies migrations. On the local Docker path that is the Postgres superuser (`backend/db-init/04-migrations.sh` runs during container init as `POSTGRES_USER`), so locally the view is superuser-owned and RLS **is** bypassed through it. On RDS, migrations run as `RDS_ADMIN_USER` (`scripts/apply-schema-rds.sh`, `scripts/migrate-rds.sh`), and whether that role bypasses RLS depends on the `BYPASSRLS` attribute of the master role in your engine version.

If it does bypass, any code path that touches this view — a future endpoint, a support query, or SQL injection anywhere in the app — returns **every consenting student across every college**, including name, email, CGPA, and score. That is the single highest-value dataset in the system and the exact scenario the vision says must never happen.

**Verify:**

```sql
SELECT c.relname, pg_get_userbyid(c.relowner) AS view_owner,
       r.rolsuper, r.rolbypassrls,
       (SELECT reloptions FROM pg_class WHERE relname='recruiter_candidates') AS opts
FROM pg_class c JOIN pg_roles r ON r.oid = c.relowner
WHERE c.relname = 'recruiter_candidates';
```

If `rolsuper` or `rolbypassrls` is true, the bypass is real.

**Fix.** The view has **no consumer** — nothing in `backend/` or `frontend/` references it, verified by grep. So the correct action is to drop it and reintroduce it, with `security_invoker = true` and behind the network access layer, when the recruiter console actually exists. Migration `0008` in this bundle does that, with the `security_invoker` variant included but commented for when it is needed. Building a cross-tenant read surface eleven months before its consumer is exactly the Phase-2-leaking-into-Phase-1 pattern the vision warns about.

---

## F-2 — Draft and closed drives are visible to students · High

**Where:** `backend/app/routers/portal.py::my_drives`

```python
drives = conn.execute(text("""
    SELECT id, name, category, package, deadline, status,
           min_cgpa, max_backlogs, eligible_branches, eligibility_rules
    FROM companies ORDER BY package DESC NULLS LAST
""")).mappings().all()
```

There is no `WHERE status = 1`. RLS scopes this to the student's college but says nothing about drive status, so `GET /api/me/drives` returns **draft (0) and closed (2) drives along with open ones**, each with name, category, package and a computed eligibility verdict.

**Impact.** A drive in draft is one the placement cell has not committed to — a company still negotiating, a package not finalised, a visit not confirmed. Students seeing it produces exactly the kind of "why did the Google drive disappear?" incident that destroys a placement cell's credibility with both students and the recruiter. The client currently receives `status` and may or may not filter it, but the data has already left the server; anyone can read it from the network tab.

**Fix.** Filter server-side: `WHERE status = 1`. Optionally return closed drives in a separate, clearly-labelled section. Add a test asserting a draft drive never appears in a student's response. This is a two-line fix and should go in before any pilot.

---

## F-3 — Activation codes are bulk-exportable plaintext credentials · High

**Where:** `students.activation_code` (plaintext column), `backend/app/routers/students_admin.py::unclaimed_codes`, `backend/app/routers/auth_routes.py::claim_account`

The claim flow accepts `college_slug + roll_no + activation_code` and creates a login with a caller-chosen password. The code is therefore a **credential**. It is stored in plaintext, never expires, and `GET /api/students/activation-codes` returns every unclaimed one in bulk — behind `view_activation_codes`, which is a **CR-grantable** capability.

**Impact.** A CR granted that capability can claim any unclaimed student account in their branch: export the list, pick a roll number, set a password, and they are now signed in as that student. Since a CR is a fellow student who turns over annually, this is a realistic insider risk rather than a hypothetical one. It is also unauditable today — there is no record that an export happened.

Credit where due: the flow does several things right. Rate limiting by IP, a single generic failure message that doesn't reveal which component matched, `409` on already-claimed, and the code is nulled on successful claim so it is effectively single-use.

**Fix, in order of value:**

1. Store a **hash** of the code, not the code. Generate, display once at import, store `activation_code_hash`. The export then re-issues new codes rather than revealing old ones.
2. Add `activation_code_expires_at` — 30 days is generous.
3. Log every export to `audit_log` with actor, branch and row count.
4. Reconsider whether `view_activation_codes` should be CR-grantable at all. The vision lists it as a CR capability; this finding is the argument for revisiting that. A middle path: a CR may *trigger delivery* of codes to students' registered emails without ever seeing them.

---

## F-4 — Roster list silently truncates at 500 students · Medium

**Where:** `backend/app/routers/students_admin.py::list_students` — `LIMIT 500`, no pagination, no total count, no indication to the caller.

The stated target customer is a college with **500 to 5,000 students**. For most of that range this endpoint silently returns a partial roster. An officer searching for a student whose roll number sorts after the 500th row finds nothing and concludes the student is not on the platform. Silent truncation is worse than an error because it looks like an answer.

**Fix.** Return `{items, total, page}` with keyset pagination on `roll_no`; make the search path query the whole roster rather than the first page; show the count in the UI. Add a test with 1,200 seeded students.

---

## F-5 — Cohort Score is trivially gameable · Medium

**Where:** `backend/app/scoring.py`

```python
if profiles.get("github", {}).get("public_repos"):
    n = profiles["github"]["public_repos"]
    coding_signals.append(min(100, n * 5))   # 20 repos = 100
coding = max(coding_signals) if coding_signals else 0
```

`coding` is 30% of the total and is the **maximum** across four signals, one of which counts public repositories with no quality check. Creating twenty empty repositories takes about ten minutes and yields a perfect coding sub-score. None of the profile links are actually verified despite `"verified": true` appearing in the documented shape.

**Impact.** Contained today, because nothing consumes the score except the student's own view. It becomes serious the moment the score is used for ranking, recruiter visibility, or anything a student competes over — at which point the students who game it outrank the students who earned it, and the signal that is supposed to be the network's moat is worthless.

**Fix.** Weight signals by reliability (rated contest performance ≫ repository count); require non-trivial repository content (commits, stars, recency) before counting GitHub at all; actually verify handles against the public APIs and only set `verified` when a check succeeded; combine signals rather than taking `max`. Until then, label it in the UI as a personal improvement indicator, not a ranking, and do not expose it outside the student's own view.

Related: scores are stored as a mutable jsonb blob on `students`, so a weighting change silently rewrites everyone's number with no history. Move to a `score_history` table keyed by `(student_id, version, computed_at)`.

---

## F-6 — `round_progress` is unenforced and over-permissive · Medium

**Where:** `backend/db-init/01-schema.sql`

```sql
CREATE POLICY t_round_progress ON round_progress USING (
      app_role() = 'owner'
   OR (college_id = app_college() AND app_role() IN ('admin','sub_admin','student','alumni'))
);
```

Any student or alumnus in the college can read **every** row — every other student's per-round outcomes and interview feedback. This is not currently exploitable because no code reads or writes the table (verified by grep across `backend/`), but it is a loaded gun: the moment someone implements the pipeline history feature recommended in `DOMAIN_MODEL.md` §3, the leak becomes live without anyone editing the policy.

**Fix.** Tighten the policy now, before the table is used: students see only rows belonging to their own applications; `sub_admin` is branch-scoped like every other policy in the schema. Migration `0008` in this bundle does this.

---

## F-7 — Permission resolution costs a transaction per check · Medium (correctness and performance)

**Where:** `backend/app/permissions.py::get_cr_permissions`, called by `require_cr_capability`

Each capability check opens a fresh `tenant_connection`, which is a new transaction and a database round trip. Endpoints that check more than one capability pay it repeatedly, and each check is a separate transaction, so two checks in one request can theoretically observe different permission states.

**Fix.** Resolve once per request in a FastAPI dependency and cache on `request.state`. Longer term, put the resolved capability list in the JWT with a `perm_epoch` claim and a matching column on `memberships`, bumped whenever grants change, so a token issued before a revocation fails closed on its next use rather than staying valid for up to eight hours.

---

## F-8 — Rate limiter is per-process · Medium

**Where:** `backend/app/security.py::RateLimiter` — an in-memory `defaultdict(deque)`, honestly documented as "per-process only — good enough for a single-box POC".

The moment the app runs more than one Uvicorn worker or more than one container, the effective limit multiplies by the worker count and the protection quietly weakens. Nothing fails; it just stops working as intended. Move to Redis before scaling out, and add a startup warning when `workers > 1` and no shared backend is configured, so the degradation is loud rather than silent.

---

## F-9 — CORS allows every origin · Low (today) / High (after any change)

**Where:** `backend/app/main.py` — `allow_origins=["*"]`, `allow_methods=["*"]`, `allow_headers=["*"]`.

Currently low-impact: the app authenticates with a bearer token in a header rather than cookies, so a wildcard origin does not enable classic CSRF, and Caddy serves app and API from one origin anyway. It becomes dangerous the moment anything moves to cookie-based sessions, or a second origin is introduced. Set an explicit allowlist from configuration now, while it costs nothing.

---

## F-10 — Defence in depth on the roster query · Low

**Where:** `students_admin.py::unclaimed_codes` and `list_students` both rely entirely on RLS for branch scoping, with no `branch_id` predicate in the SQL. That is *correct* — RLS is the authoritative layer and it works. But it means a future change to the `t_students` policy silently widens both endpoints. Add the explicit predicate as well; belt and braces cost one line and make the intent visible to the next reader.

---

## Recommended order of work

**Before a pilot college touches it:** F-2 (two lines), F-1 (drop the unused view), F-6 (tighten policy before the table is used), F-3 steps 1–3.

**Before the tenth college:** F-4, F-7, F-8, F-9, and the automated tests below.

**Before the score is shown to anyone but its own student:** F-5.

## Two tests worth more than the fixes

Both close whole classes of future bug rather than one instance:

**Every-table isolation test.** Enumerate tables from `information_schema`, insert a row for college A and college B, then assert that a connection scoped to A sees zero of B's rows in every single table. Driven by the catalogue rather than a hand-written list, so a new table added without a policy fails the build instead of shipping.

**Every-route authorization test.** Walk `app.routes`, and fail if any route under `/api/` lacks either an explicit capability requirement or an explicit `@public` marker. This turns "we remembered to add the permission check" from a review habit into a build failure — which matters most exactly when the team is moving fast, which is exactly when a check gets forgotten.
