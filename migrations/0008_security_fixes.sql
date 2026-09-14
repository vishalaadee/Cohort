-- Migration 0008: security fixes from docs/SECURITY_REVIEW.md
--
-- Addresses F-1 (cross-tenant view), F-6 (over-permissive round_progress
-- policy) and adds the audit_log the architecture calls for in Phase 1.
--
-- Safe to run on an existing database. Every statement is idempotent.
-- Apply with:  ./scripts/migrate-rds.sh      (RDS)
--              docker compose restart backend  after re-running db-init (local)

-- ---------------------------------------------------------------------------
-- F-1: drop the cross-tenant recruiter view.
--
-- Nothing in backend/ or frontend/ references this view (verified by grep).
-- It reads across every college with no college_id predicate, and because a
-- view runs with its OWNER's privileges, a superuser-owned view bypasses the
-- Row-Level Security on students entirely -- which is the case on the local
-- Docker path, where db-init runs as POSTGRES_USER.
--
-- Reintroduce it, with security_invoker, when the recruiter console exists
-- and there is a network access layer to put in front of it. The commented
-- definition below is the correct PG15+ shape for that day.
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS recruiter_candidates;

-- WHEN PHASE 2 ARRIVES, and on PostgreSQL 15 or newer, the safe version is:
--
-- CREATE VIEW recruiter_candidates
--   WITH (security_invoker = true) AS
--   SELECT s.id, s.full_name, s.email, b.code AS branch, s.cgpa,
--          s.coding_profiles, s.cohort_score, s.attributes,
--          c.name AS college, c.slug AS college_slug
--   FROM students s
--   JOIN branches b ON b.id = s.branch_id
--   JOIN colleges c ON c.id = s.college_id
--   WHERE s.consent_recruiter_share = true
--     AND s.cohort_score IS NOT NULL;
--
-- security_invoker makes RLS evaluate against the CALLING role, so the
-- recruiter service must hold an explicit, audited, consent-checked scope
-- rather than inheriting the view owner's reach.

-- ---------------------------------------------------------------------------
-- F-6: round_progress -- students could read every student's round outcomes.
--
-- The table is currently written by no application code, so tightening it now
-- costs nothing. Doing it before the pipeline-history feature lands means the
-- feature cannot silently ship a data leak.
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS t_round_progress ON round_progress;
CREATE POLICY t_round_progress ON round_progress USING (
      app_role() = 'owner'
   OR (college_id = app_college() AND app_role() = 'admin')
   OR (college_id = app_college() AND app_role() = 'sub_admin'
       AND application_id IN (
             SELECT id FROM applications WHERE branch_id = app_branch()))
   OR (college_id = app_college() AND app_role() IN ('student','alumni')
       AND application_id IN (
             SELECT a.id FROM applications a
             JOIN students s ON s.id = a.student_id
             WHERE s.user_id = app_user()))
);

-- Pipeline history needs an actor and a timestamp to be worth anything.
ALTER TABLE round_progress
  ADD COLUMN IF NOT EXISTS actor_user_id bigint REFERENCES users(id) ON DELETE SET NULL;
ALTER TABLE round_progress
  ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now();
CREATE INDEX IF NOT EXISTS round_progress_app_idx
  ON round_progress (college_id, application_id, updated_at DESC);

-- ---------------------------------------------------------------------------
-- Audit log -- Phase 1, not Phase 2.
--
-- "Who changed this student's CGPA / marked this student placed / exported
-- the roster" is a question a placement officer asks in month two, long
-- before any recruiter exists. Append-only: no UPDATE or DELETE policy.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_log (
  id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  college_id     bigint REFERENCES colleges(id) ON DELETE CASCADE,
  actor_user_id  bigint REFERENCES users(id) ON DELETE SET NULL,
  actor_role     text,
  action         text NOT NULL,          -- 'drive.publish', 'roster.import', ...
  resource_type  text NOT NULL,          -- 'drive' | 'student' | 'application'
  resource_id    bigint,
  subject_person bigint,                 -- whose data was touched, when relevant
  detail         jsonb NOT NULL DEFAULT '{}',
  request_id     text,
  created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS audit_log_college_time_idx
  ON audit_log (college_id, created_at DESC);
CREATE INDEX IF NOT EXISTS audit_log_resource_idx
  ON audit_log (college_id, resource_type, resource_id);
CREATE INDEX IF NOT EXISTS audit_log_subject_idx
  ON audit_log (subject_person, created_at DESC);

ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS t_audit_log_read ON audit_log;
CREATE POLICY t_audit_log_read ON audit_log FOR SELECT USING (
      app_role() = 'owner'
   OR (college_id = app_college() AND app_role() = 'admin')
);
-- Any authenticated scope may APPEND its own action; nobody may rewrite one.
DROP POLICY IF EXISTS t_audit_log_append ON audit_log;
CREATE POLICY t_audit_log_append ON audit_log FOR INSERT WITH CHECK (
      app_role() = 'owner'
   OR college_id = app_college()
);

-- ---------------------------------------------------------------------------
-- Consent as a ledger (ADR-04).
--
-- The boolean on students cannot answer "what was agreed, when, under which
-- policy version, and was it later revoked". It stays as a derived cache so
-- existing queries keep working; this table becomes the source of truth.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS consent_events (
  id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  college_id     bigint NOT NULL REFERENCES colleges(id) ON DELETE CASCADE,
  student_id     bigint NOT NULL REFERENCES students(id) ON DELETE CASCADE,
  purpose        text NOT NULL,          -- 'recruiter_discovery' | 'assessment_sharing'
  granted        boolean NOT NULL,
  scope          jsonb NOT NULL DEFAULT '{}',   -- which fields, which audience
  policy_version text NOT NULL,
  actor_user_id  bigint REFERENCES users(id) ON DELETE SET NULL,
  source         text,                   -- 'student_portal' | 'import' | 'support'
  created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS consent_events_lookup_idx
  ON consent_events (student_id, purpose, created_at DESC);

ALTER TABLE consent_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE consent_events FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS t_consent_events ON consent_events;
CREATE POLICY t_consent_events ON consent_events USING (
      app_role() = 'owner'
   OR (college_id = app_college() AND app_role() = 'admin')
   OR (college_id = app_college() AND app_role() IN ('student','alumni')
       AND student_id IN (SELECT id FROM students WHERE user_id = app_user()))
) WITH CHECK (
      app_role() = 'owner'
   OR (college_id = app_college() AND app_role() IN ('student','alumni')
       AND student_id IN (SELECT id FROM students WHERE user_id = app_user()))
);

-- ---------------------------------------------------------------------------
-- Versioned score history (replaces the mutable jsonb blob as source of truth).
-- students.cohort_score stays as the latest-value cache.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS score_history (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  college_id  bigint NOT NULL REFERENCES colleges(id) ON DELETE CASCADE,
  student_id  bigint NOT NULL REFERENCES students(id) ON DELETE CASCADE,
  version     text NOT NULL,
  total       int NOT NULL CHECK (total BETWEEN 0 AND 100),
  components  jsonb NOT NULL DEFAULT '{}',
  inputs      jsonb NOT NULL DEFAULT '{}',   -- what the score was computed FROM
  computed_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (student_id, version, computed_at)
);
CREATE INDEX IF NOT EXISTS score_history_student_idx
  ON score_history (student_id, computed_at DESC);

ALTER TABLE score_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE score_history FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS t_score_history ON score_history;
CREATE POLICY t_score_history ON score_history USING (
      app_role() = 'owner'
   OR (college_id = app_college() AND app_role() = 'admin')
   OR (college_id = app_college() AND app_role() IN ('student','alumni')
       AND student_id IN (SELECT id FROM students WHERE user_id = app_user()))
);

-- ---------------------------------------------------------------------------
-- Permission epoch (F-7): lets a grant change invalidate tokens issued before
-- it, instead of waiting out the 8-hour JWT expiry.
-- ---------------------------------------------------------------------------
ALTER TABLE memberships
  ADD COLUMN IF NOT EXISTS perm_epoch int NOT NULL DEFAULT 1;

-- ---------------------------------------------------------------------------
-- Activation codes (F-3): expiry column. Hashing the code itself is an
-- application change (generate -> show once -> store hash) and is deliberately
-- NOT done here, because it needs a coordinated code change in the same
-- release. This column is the safe half.
-- ---------------------------------------------------------------------------
ALTER TABLE students
  ADD COLUMN IF NOT EXISTS activation_code_expires_at timestamptz;

-- Existing unclaimed codes get a 30-day window from now rather than living
-- forever. Adjust or remove this line if your pilot needs longer.
UPDATE students
   SET activation_code_expires_at = now() + interval '30 days'
 WHERE activation_code IS NOT NULL
   AND user_id IS NULL
   AND activation_code_expires_at IS NULL;

-- ---------------------------------------------------------------------------
-- Grants for the application role. Harmless if already held.
-- Replace app_user if your APP_DB_USER differs.
-- ---------------------------------------------------------------------------
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_user') THEN
    GRANT SELECT, INSERT, UPDATE, DELETE
      ON audit_log, consent_events, score_history TO app_user;
    GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_user;
  END IF;
END $$;
