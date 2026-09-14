-- Migration 0003: configurable eligibility & placement policy
-- Fresh installs: fold into 01-schema.sql later; existing DBs: run this.

-- Layer 1 — extensible student attributes.
-- Core columns (cgpa, backlogs) stay; everything college-specific lives here.
ALTER TABLE students ADD COLUMN IF NOT EXISTS attributes jsonb NOT NULL DEFAULT '{}';
-- e.g. {"tenth_pct": 88.4, "twelfth_pct": 91.2, "active_backlogs": 0, "gap_years": 0}

-- The registry that drives the admin rule-builder dropdowns and lets the CSV
-- import map extra columns. Admin-managed, per college.
CREATE TABLE IF NOT EXISTS attribute_defs (
  id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  college_id bigint NOT NULL REFERENCES colleges(id) ON DELETE CASCADE,
  key        text NOT NULL,           -- 'tenth_pct'  (also the CSV column name)
  label      text NOT NULL,           -- '10th percentage'
  data_type  text NOT NULL CHECK (data_type IN ('number','text','boolean')),
  UNIQUE (college_id, key)
);
ALTER TABLE attribute_defs ENABLE ROW LEVEL SECURITY;
ALTER TABLE attribute_defs FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS t_attribute_defs ON attribute_defs;
CREATE POLICY t_attribute_defs ON attribute_defs
  USING (app_role() = 'owner' OR college_id = app_college());

-- Layer 2 — per-drive rule tree. NULL = fall back to the legacy three columns
-- (min_cgpa / max_backlogs / eligible_branches), so nothing breaks.
ALTER TABLE companies ADD COLUMN IF NOT EXISTS eligibility_rules jsonb;

-- Layer 3 — college-wide placement policy (parameterized templates).
ALTER TABLE colleges ADD COLUMN IF NOT EXISTS placement_policy jsonb NOT NULL DEFAULT '{}';
-- e.g. {"one_offer": false,
--       "slabs": [{"name":"S1","max_lpa":5},{"name":"S2","max_lpa":10},{"name":"S3"}],
--       "upgrade": "higher_slab",      -- or "multiplier" | "both" | "none"
--       "multiplier": 1.5,
--       "max_offers": 2}
