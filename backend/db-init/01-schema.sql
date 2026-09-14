-- ============================================================
-- Placement platform — multi-tenant core schema + Row-Level Security
-- Model: POOLED multi-tenancy. Every tenant row carries college_id.
-- Isolation is enforced twice: in app code AND here via Postgres RLS,
-- so an application bug cannot leak one college's data to another.
-- Target: PostgreSQL 14+  (works on self-hosted PG or Supabase).
-- ============================================================

-- ------------------------------------------------------------
-- 0. Per-request session context
-- The API sets these GUCs at the start of every request, from the JWT:
--   SET app.role       = 'admin';      -- owner|admin|sub_admin|student|alumni
--   SET app.college_id = '12';         -- tenant; empty for owner
--   SET app.branch_id  = '4';          -- set for sub_admin/student
--   SET app.user_id    = '900';        -- the acting user
-- Use SET LOCAL inside a transaction so it can't leak across pooled conns.
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION app_role() RETURNS text
  LANGUAGE sql STABLE AS $$ SELECT current_setting('app.role', true) $$;

CREATE OR REPLACE FUNCTION app_college() RETURNS bigint
  LANGUAGE sql STABLE AS $$ SELECT NULLIF(current_setting('app.college_id', true), '')::bigint $$;

CREATE OR REPLACE FUNCTION app_branch() RETURNS bigint
  LANGUAGE sql STABLE AS $$ SELECT NULLIF(current_setting('app.branch_id', true), '')::bigint $$;

CREATE OR REPLACE FUNCTION app_user() RETURNS bigint
  LANGUAGE sql STABLE AS $$ SELECT NULLIF(current_setting('app.user_id', true), '')::bigint $$;

-- ------------------------------------------------------------
-- 1. Tenancy
-- ------------------------------------------------------------
CREATE TABLE colleges (
  id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name         text NOT NULL,
  slug         text UNIQUE NOT NULL,            -- subdomain / path segment
  email_domain text,                            -- e.g. sjce.ac.in -> SSO auto-map
  status       text NOT NULL DEFAULT 'pending', -- pending|active|suspended
  created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE branches (
  id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  college_id bigint NOT NULL REFERENCES colleges(id) ON DELETE CASCADE,
  code       text NOT NULL,                     -- CSE, ISE, ECE...
  name       text NOT NULL,
  UNIQUE (college_id, code)
);

-- ------------------------------------------------------------
-- 2. Identity — auth itself lives in the IdP (Google/Keycloak/Supabase).
-- users = profile + link to the external subject. memberships = role@scope.
-- ------------------------------------------------------------
CREATE TABLE users (
  id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  email            text UNIQUE NOT NULL,
  full_name        text,
  external_auth_id text UNIQUE,                 -- 'sub' claim from Google (SSO users)
  password_hash    text,                        -- bcrypt (password users; NULL for SSO-only)
  created_at       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE memberships (
  id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id    bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  college_id bigint REFERENCES colleges(id) ON DELETE CASCADE,  -- NULL for owner
  branch_id  bigint REFERENCES branches(id) ON DELETE SET NULL, -- set for sub_admin
  role       text NOT NULL CHECK (role IN ('owner','admin','sub_admin','student','alumni')),
  status     text NOT NULL DEFAULT 'active',
  UNIQUE (user_id, college_id, role)
);

-- ------------------------------------------------------------
-- 3. Roster & domain  (all tenant-scoped via college_id)
-- students = source of truth for "who is a real student" (bulk import / SIS).
-- user_id is linked lazily when the student first signs in via SSO.
-- ------------------------------------------------------------
CREATE TABLE students (
  id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  college_id bigint NOT NULL REFERENCES colleges(id) ON DELETE CASCADE,
  branch_id  bigint NOT NULL REFERENCES branches(id) ON DELETE CASCADE,
  user_id    bigint REFERENCES users(id) ON DELETE SET NULL,       -- null until signup
  roll_no    text NOT NULL,                     -- URN/USN
  email      text NOT NULL,
  full_name  text,
  cgpa       numeric(4,2),
  backlogs   int NOT NULL DEFAULT 0,
  verified   boolean NOT NULL DEFAULT false,
  activation_code text,                         -- claim-account flow (colleges without Google)
  claimed_at      timestamptz,
  UNIQUE (college_id, roll_no)
);
CREATE INDEX ON students (college_id, branch_id);
CREATE INDEX ON students (college_id, email);

CREATE TABLE companies (
  id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  college_id        bigint NOT NULL REFERENCES colleges(id) ON DELETE CASCADE,
  name              text NOT NULL,
  category          text,                        -- tier1|tier2|dream|core|internship
  package           numeric(12,2),
  min_cgpa          numeric(4,2) NOT NULL DEFAULT 0,
  max_backlogs      int NOT NULL DEFAULT 0,
  eligible_branches text[] NOT NULL DEFAULT '{}',
  deadline          timestamptz,
  status            int NOT NULL DEFAULT 0,      -- 0 draft, 1 open, 2 closed
  created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON companies (college_id, status);

CREATE TABLE applications (
  id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  college_id    bigint NOT NULL REFERENCES colleges(id) ON DELETE CASCADE,
  branch_id     bigint NOT NULL REFERENCES branches(id) ON DELETE CASCADE,
  company_id    bigint NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  student_id    bigint NOT NULL REFERENCES students(id) ON DELETE CASCADE,
  current_round text NOT NULL DEFAULT 'resume_screening',
  status        text NOT NULL DEFAULT 'active',  -- active|placed|rejected|withdrawn
  created_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_id, student_id)
);
CREATE INDEX ON applications (college_id, company_id);
CREATE INDEX ON applications (college_id, branch_id, status);

CREATE TABLE round_progress (
  id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  college_id     bigint NOT NULL REFERENCES colleges(id) ON DELETE CASCADE,
  application_id bigint NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
  round          text NOT NULL,                  -- resume_screening..hr, final_placement
  status         text NOT NULL,                  -- cleared|failed|pending|absent
  feedback       text,
  updated_at     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (application_id, round)
);

CREATE TABLE offers (
  id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  college_id bigint NOT NULL REFERENCES colleges(id) ON DELETE CASCADE,
  student_id bigint NOT NULL REFERENCES students(id) ON DELETE CASCADE,
  company_id bigint NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  category   text,
  is_special boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON offers (college_id, company_id);

-- Interview-experience knowledge base (your cheap differentiator)
CREATE TABLE feedback (
  id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  college_id bigint NOT NULL REFERENCES colleges(id) ON DELETE CASCADE,
  student_id bigint REFERENCES students(id) ON DELETE SET NULL,
  company_id bigint NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  role       text,
  ctc        numeric(12,2),
  rounds     text,
  difficulty int CHECK (difficulty BETWEEN 1 AND 5),
  topics     text,
  tips       text,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON feedback (college_id, company_id);

-- ============================================================
-- 4. Row-Level Security
-- Gotchas handled below:
--   * The app MUST connect as a NON-superuser role — superusers bypass RLS.
--   * Table owners also bypass unless you FORCE it — so we FORCE on every table.
--   * Helper functions are STABLE so the planner can cache them per statement.
-- The pattern per table = owner-sees-all + tenant match (+ branch/self where
-- relevant). Replicate the same three shapes onto any new tenant table.
-- ============================================================

-- --- Pure tenant tables: branches, companies, offers, feedback ---
ALTER TABLE branches  ENABLE ROW LEVEL SECURITY; ALTER TABLE branches  FORCE ROW LEVEL SECURITY;
ALTER TABLE companies ENABLE ROW LEVEL SECURITY; ALTER TABLE companies FORCE ROW LEVEL SECURITY;
ALTER TABLE offers    ENABLE ROW LEVEL SECURITY; ALTER TABLE offers    FORCE ROW LEVEL SECURITY;
ALTER TABLE feedback  ENABLE ROW LEVEL SECURITY; ALTER TABLE feedback  FORCE ROW LEVEL SECURITY;

CREATE POLICY t_branches ON branches USING (app_role() = 'owner' OR college_id = app_college());
CREATE POLICY t_companies ON companies USING (app_role() = 'owner' OR college_id = app_college());
CREATE POLICY t_offers   ON offers   USING (app_role() = 'owner' OR college_id = app_college());
CREATE POLICY t_feedback ON feedback USING (app_role() = 'owner' OR college_id = app_college());

-- --- colleges: owner sees all; a member sees only their own college ---
ALTER TABLE colleges ENABLE ROW LEVEL SECURITY; ALTER TABLE colleges FORCE ROW LEVEL SECURITY;
CREATE POLICY t_colleges ON colleges USING (app_role() = 'owner' OR id = app_college());

-- --- students: owner all / admin whole college / sub_admin own branch /
--     student & alumni only their own row ---
ALTER TABLE students ENABLE ROW LEVEL SECURITY; ALTER TABLE students FORCE ROW LEVEL SECURITY;
CREATE POLICY t_students ON students USING (
      app_role() = 'owner'
   OR (college_id = app_college() AND app_role() = 'admin')
   OR (college_id = app_college() AND app_role() = 'sub_admin' AND branch_id = app_branch())
   OR (college_id = app_college() AND app_role() IN ('student','alumni') AND user_id = app_user())
);

-- --- applications: same shape, branch-scoped for sub_admin, self for student ---
ALTER TABLE applications ENABLE ROW LEVEL SECURITY; ALTER TABLE applications FORCE ROW LEVEL SECURITY;
CREATE POLICY t_applications ON applications USING (
      app_role() = 'owner'
   OR (college_id = app_college() AND app_role() = 'admin')
   OR (college_id = app_college() AND app_role() = 'sub_admin' AND branch_id = app_branch())
   OR (college_id = app_college() AND app_role() = 'student'
       AND student_id IN (SELECT id FROM students WHERE user_id = app_user()))
);

-- --- round_progress: no college_id filter needed beyond joining its parent
--     application, but we keep college_id on the row for a cheap direct check ---
ALTER TABLE round_progress ENABLE ROW LEVEL SECURITY; ALTER TABLE round_progress FORCE ROW LEVEL SECURITY;
CREATE POLICY t_round_progress ON round_progress USING (
      app_role() = 'owner'
   OR (college_id = app_college() AND app_role() IN ('admin','sub_admin','student','alumni'))
);

-- --- users: a person may read/update their own row; owner (and the auth
-- service, which runs with the 'owner' system scope) sees all. ---
ALTER TABLE users ENABLE ROW LEVEL SECURITY; ALTER TABLE users FORCE ROW LEVEL SECURITY;
CREATE POLICY t_users ON users USING (app_role() = 'owner' OR id = app_user());

-- --- memberships / users are identity tables; keep them app-managed.
-- A user may read their own memberships; owner reads all. ---
ALTER TABLE memberships ENABLE ROW LEVEL SECURITY; ALTER TABLE memberships FORCE ROW LEVEL SECURITY;
CREATE POLICY t_memberships ON memberships USING (app_role() = 'owner' OR user_id = app_user());

-- ============================================================
-- 5. The application database role (NON-superuser, so RLS applies)
-- Run migrations as the owner; run the API as app_user.
-- ============================================================
-- CREATE ROLE app_user LOGIN PASSWORD 'change-me';
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user;
-- GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO app_user;
-- ALTER DEFAULT PRIVILEGES IN SCHEMA public
--   GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_user;
