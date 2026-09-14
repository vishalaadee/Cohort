-- Migration 0009: buckets, reminders, exports, per-drive customisation,
-- idempotent notifications, entitlements, junior/final-year split.
--
-- Additive and idempotent. Apply after 0008.
--   RDS:   ./scripts/migrate-rds.sh
--   local: docker exec -i infra-db-1 psql -U postgres -d placement < migrations/0009_placement_features.sql

-- ---------------------------------------------------------------------------
-- 1. Buckets — tier1/tier2/dream/core as DATA, with each college's own names.
--    companies.category already holds a text key; this gives it meaning.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS buckets (
  id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  college_id   bigint NOT NULL REFERENCES colleges(id) ON DELETE CASCADE,
  key          text NOT NULL,                       -- stable: 'tier1'
  label        text NOT NULL,                       -- shown:  'Tier 1'
  aliases      text[] NOT NULL DEFAULT '{}',        -- 'Super Dream', 'A+'
  min_package  numeric(12,2),
  max_package  numeric(12,2),
  counts_toward_cap boolean NOT NULL DEFAULT true,  -- uses up an offer slot
  ignores_cap  boolean NOT NULL DEFAULT false,      -- placed students may still sit
  sort_order   int NOT NULL DEFAULT 0,
  created_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (college_id, key)
);
ALTER TABLE buckets ENABLE ROW LEVEL SECURITY;
ALTER TABLE buckets FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS t_buckets ON buckets;
CREATE POLICY t_buckets ON buckets
  USING (app_role() = 'owner' OR college_id = app_college())
  WITH CHECK (app_role() = 'owner'
              OR (college_id = app_college() AND app_role() = 'admin'));

-- Seed the four common buckets for every existing college that has none.
INSERT INTO buckets (college_id, key, label, min_package, max_package,
                     counts_toward_cap, ignores_cap, sort_order)
SELECT c.id, v.key, v.label, v.minp, v.maxp, v.cap, v.ign, v.ord
FROM colleges c
CROSS JOIN (VALUES
  ('tier1','Tier 1', 2000000::numeric, NULL::numeric, true,  false, 1),
  ('tier2','Tier 2',  800000::numeric, 1500000::numeric, true,  false, 2),
  ('dream','Dream',  1500000::numeric, NULL::numeric, false, true,  3),
  ('core', 'Core',        NULL::numeric, 1000000::numeric, true,  false, 4),
  ('internship','Internship', NULL::numeric, NULL::numeric, false, true, 5)
) AS v(key,label,minp,maxp,cap,ign,ord)
WHERE NOT EXISTS (SELECT 1 FROM buckets b WHERE b.college_id = c.id)
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------------
-- 2. Per-drive customisation.
--    Central policy is the default. A drive only overrides when the officer
--    answers "yes" to "any customisation for this company?".
--    eligibility_rules (0003) already holds custom ELIGIBILITY; this adds the
--    custom POLICY override and the practical drive fields.
-- ---------------------------------------------------------------------------
ALTER TABLE companies ADD COLUMN IF NOT EXISTS role_title   text;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS test_date    timestamptz;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS venue        text;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS custom_policy jsonb;
-- NULL custom_policy  => use the college's central placement_policy.
-- e.g. {"upgrade":"multiplier","multiplier":2.0,"reason":"Company asked"}
ALTER TABLE companies ADD COLUMN IF NOT EXISTS restriction_note text;
-- Plain-language reason shown to students when a company-specific rule
-- blocks them (e.g. "Open to women candidates only"). Stored with the
-- eligibility rule that enforces it, never instead of it.
ALTER TABLE companies ADD COLUMN IF NOT EXISTS published_at timestamptz;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS published_by bigint REFERENCES users(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS companies_college_status_idx ON companies (college_id, status, deadline);

-- ---------------------------------------------------------------------------
-- 3. Reminders — private to the staff member who created them.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reminders (
  id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  college_id   bigint NOT NULL REFERENCES colleges(id) ON DELETE CASCADE,
  user_id      bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title        text NOT NULL,
  body         text,
  due_at       timestamptz NOT NULL,
  repeat_rule  text CHECK (repeat_rule IS NULL OR repeat_rule IN ('weekly','monthly')),
  company_id   bigint REFERENCES companies(id) ON DELETE SET NULL,
  done_at      timestamptz,
  notified_at  timestamptz,
  created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS reminders_due_idx ON reminders (college_id, user_id, done_at, due_at);
ALTER TABLE reminders ENABLE ROW LEVEL SECURITY;
ALTER TABLE reminders FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS t_reminders ON reminders;
-- A reminder is a private note to self. Not visible to other staff, ever to CRs.
CREATE POLICY t_reminders ON reminders
  USING (app_role() = 'owner'
         OR (college_id = app_college() AND user_id = app_user()))
  WITH CHECK (app_role() = 'owner'
              OR (college_id = app_college() AND user_id = app_user()));

-- ---------------------------------------------------------------------------
-- 4. Export templates — which columns the placement cell wants in a sheet.
--    The column KEYS are validated against a server-side allow-list in
--    backend/app/routers/placement.py. They never reach SQL as identifiers.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS export_templates (
  id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  college_id bigint NOT NULL REFERENCES colleges(id) ON DELETE CASCADE,
  name       text NOT NULL,
  columns    jsonb NOT NULL,
  is_default boolean NOT NULL DEFAULT false,
  created_by bigint REFERENCES users(id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (college_id, name)
);
ALTER TABLE export_templates ENABLE ROW LEVEL SECURITY;
ALTER TABLE export_templates FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS t_export_templates ON export_templates;
CREATE POLICY t_export_templates ON export_templates
  USING (app_role() = 'owner'
         OR (college_id = app_college() AND app_role() IN ('admin','sub_admin')))
  WITH CHECK (app_role() = 'owner'
              OR (college_id = app_college() AND app_role() = 'admin'));

INSERT INTO export_templates (college_id, name, columns, is_default)
SELECT c.id, 'Short info',
       '["roll_no","full_name","branch","email","cgpa"]'::jsonb, true
FROM colleges c
WHERE NOT EXISTS (SELECT 1 FROM export_templates t
                  WHERE t.college_id = c.id AND t.name = 'Short info')
ON CONFLICT DO NOTHING;

INSERT INTO export_templates (college_id, name, columns, is_default)
SELECT c.id, 'Full info',
       '["roll_no","full_name","branch","email","cgpa","backlogs","tenth_pct","twelfth_pct","current_round","status","applied_at"]'::jsonb, false
FROM colleges c
WHERE NOT EXISTS (SELECT 1 FROM export_templates t
                  WHERE t.college_id = c.id AND t.name = 'Full info')
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------------
-- 5. Outbound notification log — makes every send idempotent.
--    A second click, a retry or a reconnecting client finds the row and
--    does nothing. Same shape as the escalation guard added in 0006.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS notification_log (
  id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  college_id   bigint NOT NULL REFERENCES colleges(id) ON DELETE CASCADE,
  kind         text NOT NULL CHECK (kind IN
                 ('drive_published','test_reminder','placed_congrats','feedback_reminder','reminder_due')),
  resource_type text NOT NULL,
  resource_id  bigint NOT NULL,
  dedupe_key   text NOT NULL,
  recipients   int NOT NULL DEFAULT 0,
  sent_by      bigint REFERENCES users(id) ON DELETE SET NULL,
  sent_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (college_id, dedupe_key)
);
CREATE INDEX IF NOT EXISTS notification_log_res_idx
  ON notification_log (college_id, resource_type, resource_id, kind);
ALTER TABLE notification_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE notification_log FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS t_notification_log ON notification_log;
CREATE POLICY t_notification_log ON notification_log
  USING (app_role() = 'owner' OR college_id = app_college())
  WITH CHECK (app_role() = 'owner'
              OR (college_id = app_college() AND app_role() = 'admin'));

-- ---------------------------------------------------------------------------
-- 6. Where announcements go. Per college, verified before use.
-- ---------------------------------------------------------------------------
ALTER TABLE colleges ADD COLUMN IF NOT EXISTS notify_groups jsonb NOT NULL DEFAULT '{}';
-- {"students":{"email":"placements-2027@demo.ac.in","verified_at":"..."},
--  "juniors" :{"email":"students-all@demo.ac.in","verified_at":null}}

-- ---------------------------------------------------------------------------
-- 7. Entitlements — what this college has bought. NOT permissions.
--    A permission answers "may this person"; an entitlement answers
--    "has this college paid for it". Both are checked, server-side.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS entitlements (
  college_id bigint NOT NULL REFERENCES colleges(id) ON DELETE CASCADE,
  feature    text NOT NULL,
  enabled    boolean NOT NULL DEFAULT false,
  enabled_at timestamptz,
  enabled_by bigint REFERENCES users(id) ON DELETE SET NULL,
  PRIMARY KEY (college_id, feature)
);
ALTER TABLE entitlements ENABLE ROW LEVEL SECURITY;
ALTER TABLE entitlements FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS t_entitlements ON entitlements;
-- Readable by anyone in the college (the UI needs to know what is locked);
-- writable by nobody through the app — only the platform operator.
CREATE POLICY t_entitlements ON entitlements
  USING (app_role() = 'owner' OR college_id = app_college())
  WITH CHECK (app_role() = 'owner');

-- ---------------------------------------------------------------------------
-- 8. Juniors are students in a non-final year — NOT a separate role.
--    Adding a role would duplicate every RLS policy in the schema for a
--    difference that is one column and a WHERE clause.
-- ---------------------------------------------------------------------------
ALTER TABLE students ADD COLUMN IF NOT EXISTS batch_year   int;
ALTER TABLE students ADD COLUMN IF NOT EXISTS program_years int NOT NULL DEFAULT 4;
CREATE INDEX IF NOT EXISTS students_batch_idx ON students (college_id, batch_year);

CREATE OR REPLACE FUNCTION is_final_year(batch int) RETURNS boolean
  LANGUAGE sql STABLE AS $$
    SELECT batch IS NULL OR batch <= EXTRACT(YEAR FROM now())::int
           + CASE WHEN EXTRACT(MONTH FROM now())::int >= 7 THEN 1 ELSE 0 END
  $$;
-- NULL batch_year = treated as final year, so existing rosters keep working.

-- ---------------------------------------------------------------------------
-- 9. Grants
-- ---------------------------------------------------------------------------
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_user') THEN
    GRANT SELECT, INSERT, UPDATE, DELETE ON
      buckets, reminders, export_templates, notification_log, entitlements TO app_user;
    GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_user;
  END IF;
END $$;
