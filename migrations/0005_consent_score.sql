-- Migration 0005: consent, coding profiles, Cohort Score
-- The bridge from SaaS to marketplace — data collected with consent.

-- Student consent: opt-in for recruiter profile sharing (DPDP-compliant)
ALTER TABLE students ADD COLUMN IF NOT EXISTS
  consent_recruiter_share boolean NOT NULL DEFAULT false;
ALTER TABLE students ADD COLUMN IF NOT EXISTS
  consent_updated_at timestamptz;

-- Public coding profiles (verified via public APIs — no partnerships needed)
ALTER TABLE students ADD COLUMN IF NOT EXISTS coding_profiles jsonb NOT NULL DEFAULT '{}';
-- e.g. {"codeforces": {"handle":"sanjay_cf","rating":1450,"verified":true},
--       "codechef":   {"handle":"sanjay_cc","rating":1680,"verified":true},
--       "leetcode":   {"handle":"sanjayLC","solved":220,"verified":true},
--       "github":     {"handle":"sanjayhostel0","public_repos":12,"verified":true}}

-- Cohort Score: computed, explainable, student-visible
ALTER TABLE students ADD COLUMN IF NOT EXISTS cohort_score jsonb;
-- e.g. {"total":74,"components":{"academics":82,"coding":68,"resume":71,"engagement":75},
--       "computed_at":"2026-07-21T...","version":"v0"}

-- Recruiter-facing views: only students who opted in
CREATE OR REPLACE VIEW recruiter_candidates AS
  SELECT s.id, s.full_name, s.email, b.code AS branch, s.cgpa,
         s.coding_profiles, s.cohort_score,
         s.attributes, c.name AS college, c.slug AS college_slug
  FROM students s
  JOIN branches b ON b.id = s.branch_id
  JOIN colleges c ON c.id = s.college_id
  WHERE s.consent_recruiter_share = true
    AND s.cohort_score IS NOT NULL;
-- No RLS on the view — it's meant for the future recruiter portal.
-- Access controlled at the API layer (recruiter auth, not yet built).

COMMENT ON COLUMN students.consent_recruiter_share IS
  'Student opted in to share their verified profile with recruiters on Cohort. Revocable anytime.';
COMMENT ON COLUMN students.cohort_score IS
  'Computed by the platform. Student-visible + explainable. Shared with recruiters only if consent_recruiter_share = true.';
