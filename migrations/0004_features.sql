-- Migration 0004: current-version feature tables (all tenant-scoped)

-- Resume per student (bytea for the pilot; swap to S3/MinIO at scale — the
-- API surface stays identical, only storage changes)
CREATE TABLE IF NOT EXISTS resumes (
  id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  college_id bigint NOT NULL REFERENCES colleges(id) ON DELETE CASCADE,
  student_id bigint NOT NULL UNIQUE REFERENCES students(id) ON DELETE CASCADE,
  filename   text NOT NULL,
  mime       text NOT NULL,
  data       bytea NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- "Request to edit information": student proposes, admin approves/rejects
CREATE TABLE IF NOT EXISTS edit_requests (
  id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  college_id      bigint NOT NULL REFERENCES colleges(id) ON DELETE CASCADE,
  student_id      bigint NOT NULL REFERENCES students(id) ON DELETE CASCADE,
  field           text NOT NULL,          -- cgpa|backlogs|full_name|email|attr:<key>
  current_value   text,
  requested_value text NOT NULL,
  note            text,
  status          text NOT NULL DEFAULT 'pending',  -- pending|approved|rejected
  created_at      timestamptz NOT NULL DEFAULT now()
);

-- Q&A: students post; sub-admin (CR) reads branch questions and escalates;
-- admin (PO) answers. Answered questions are visible to the whole college.
CREATE TABLE IF NOT EXISTS questions (
  id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  college_id bigint NOT NULL REFERENCES colleges(id) ON DELETE CASCADE,
  branch_id  bigint REFERENCES branches(id) ON DELETE SET NULL,
  student_id bigint REFERENCES students(id) ON DELETE SET NULL,
  title      text NOT NULL,
  body       text,
  status     text NOT NULL DEFAULT 'open',  -- open|escalated|answered
  answer     text,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- Notes + calendar for the placement cell: visits, tests, deadlines, notes
CREATE TABLE IF NOT EXISTS company_notes (
  id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  college_id bigint NOT NULL REFERENCES colleges(id) ON DELETE CASCADE,
  company_id bigint REFERENCES companies(id) ON DELETE SET NULL,
  note_date  date NOT NULL,
  kind       text NOT NULL DEFAULT 'note',  -- visit|test|deadline|note
  title      text NOT NULL,
  body       text,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- RLS: same shapes as the rest of the schema
ALTER TABLE resumes ENABLE ROW LEVEL SECURITY; ALTER TABLE resumes FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS t_resumes ON resumes;
CREATE POLICY t_resumes ON resumes USING (
     app_role() = 'owner'
  OR (college_id = app_college() AND app_role() IN ('admin','sub_admin'))
  OR (college_id = app_college() AND app_role() IN ('student','alumni')
      AND student_id IN (SELECT id FROM students WHERE user_id = app_user()))
);

ALTER TABLE edit_requests ENABLE ROW LEVEL SECURITY; ALTER TABLE edit_requests FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS t_edit_requests ON edit_requests;
CREATE POLICY t_edit_requests ON edit_requests USING (
     app_role() = 'owner'
  OR (college_id = app_college() AND app_role() IN ('admin','sub_admin'))
  OR (college_id = app_college() AND app_role() = 'student'
      AND student_id IN (SELECT id FROM students WHERE user_id = app_user()))
);

ALTER TABLE questions ENABLE ROW LEVEL SECURITY; ALTER TABLE questions FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS t_questions ON questions;
CREATE POLICY t_questions ON questions USING (
     app_role() = 'owner'
  OR (college_id = app_college() AND app_role() = 'admin')
  OR (college_id = app_college() AND app_role() = 'sub_admin' AND branch_id = app_branch())
  OR (college_id = app_college() AND app_role() IN ('student','alumni')
      AND (status = 'answered'
           OR student_id IN (SELECT id FROM students WHERE user_id = app_user())))
);

ALTER TABLE company_notes ENABLE ROW LEVEL SECURITY; ALTER TABLE company_notes FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS t_company_notes ON company_notes;
CREATE POLICY t_company_notes ON company_notes USING (
     app_role() = 'owner'
  OR (college_id = app_college() AND app_role() IN ('admin','sub_admin'))
);
