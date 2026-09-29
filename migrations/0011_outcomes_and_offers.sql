-- Migration 0011: student outcomes, proof documents, and an offer lifecycle.
--
-- Additive and idempotent. Apply after 0010.
--   RDS:   ./scripts/migrate-rds.sh
--   local: docker exec -i infra-db-1 psql -U postgres -d placement < migrations/0011_outcomes_and_offers.sql
--
-- ===========================================================================
-- WHY THIS EXISTS
--
-- Until now the only outcome this platform could record was "an application
-- reached status = placed". That is not what any accreditation body asks for,
-- and the gap is not cosmetic:
--
--   NAAC 5.2.1  placed / (final-year students MINUS those in higher education)
--   NAAC 5.2.2  higher education progression, with a LINK TO PROOF per student
--   NAAC 5.2.3  students qualifying NET/SLET/GATE/UPSC, with certificates
--   NBA  4.6    (placed + higher studies + entrepreneurship) / final-year
--   NIRF GPH    % placed and % higher studies, 3-year average
--   NIRF GMS    MEDIAN SALARY of graduates, 3-year average
--
-- Three consequences for the schema:
--
--   1. Higher studies and entrepreneurship must be first-class outcomes. All
--      three bodies count them; most placement cells record neither, which is
--      why colleges systematically UNDER-report themselves. NIRF's own guidance
--      gives the example of a college with 70% placement and 12% higher studies
--      that reports 70% when its GPH-eligible rate is 85%.
--
--   2. Outcomes must carry evidence. NAAC 5.2.2 wants a link to proof of
--      continuation; 5.2.3 wants qualifying certificates. An aggregate number
--      with no artefact behind it is not submittable.
--
--   3. Salary must live on the offer, not on the drive. `companies.package` is
--      what was advertised. NIRF asks for the median of what graduates actually
--      got, and those differ.
--
-- And a fourth thing learned the hard way in 2024-26: an offer is not a
-- boolean. Offers get revoked and joining dates get deferred by 6-12 months. A
-- schema where `placed` is terminal will misreport a college whose offers were
-- pulled, and NAAC asks what happened, not what was promised.
-- ===========================================================================


-- ---------------------------------------------------------------------------
-- 1. student_outcomes — what actually became of each student.
--
--    One student may have SEVERAL outcomes: a student can be placed AND have
--    cleared GATE, and NAAC counts those under different metrics (5.2.1 and
--    5.2.3). So this is not one row per student.
--
--    But every student has exactly one HEADLINE classification, because
--    NAAC 5.2.1 removes higher-education students from its denominator and a
--    student cannot be in both the numerator and the exclusion. That is what
--    `is_primary` is for, enforced by a partial unique index below.
--
--    `batch_year` is denormalised from students deliberately. Every report in
--    this product is year-wise (NAAC wants five separate years), and carrying
--    the year here keeps the reporting queries from joining students just to
--    filter, which matters when the same query runs per branch per batch.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS student_outcomes (
  id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  college_id     bigint NOT NULL REFERENCES colleges(id) ON DELETE CASCADE,
  branch_id      bigint          REFERENCES branches(id) ON DELETE SET NULL,
  student_id     bigint NOT NULL REFERENCES students(id) ON DELETE CASCADE,
  batch_year     int,

  kind           text NOT NULL CHECK (kind IN (
                   'placed_campus',      -- through a drive on this platform
                   'placed_offcampus',   -- got a job independently; still counts
                   'higher_studies',     -- MTech/MS/MBA/PhD — NAAC 5.2.2
                   'entrepreneurship',   -- started a venture — NBA 4.6 'Z'
                   'competitive_exam',   -- GATE/NET/UPSC etc — NAAC 5.2.3
                   'not_placed',         -- seeking, not yet placed
                   'unavailable'         -- not seeking (family business, health, …)
                 )),
  is_primary     boolean NOT NULL DEFAULT false,

  -- employment
  employer_name  text,
  role_title     text,
  company_id     bigint REFERENCES companies(id) ON DELETE SET NULL,
  annual_ctc     numeric(12,2),     -- actual, not the advertised package

  -- higher studies
  institution_name text,
  program_name     text,

  -- competitive exam
  exam_name      text,
  exam_score     text,

  -- entrepreneurship
  venture_name   text,
  venture_reg_no text,

  effective_date date,
  source         text NOT NULL DEFAULT 'officer'
                 CHECK (source IN ('self_reported','officer','derived')),

  -- An assessor will ask who confirmed this. Self-reported outcomes are useful
  -- for collection and worthless as evidence until someone in the cell signs
  -- them off, so the two states are kept distinct rather than collapsed.
  verified       boolean NOT NULL DEFAULT false,
  verified_by    bigint REFERENCES users(id) ON DELETE SET NULL,
  verified_at    timestamptz,

  notes          text,
  created_by     bigint REFERENCES users(id) ON DELETE SET NULL,
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now()
);

-- One headline outcome per student. A partial unique index rather than a
-- constraint, so the non-primary rows (a GATE qualification alongside a job)
-- are unrestricted.
CREATE UNIQUE INDEX IF NOT EXISTS student_outcomes_one_primary
  ON student_outcomes (student_id) WHERE is_primary;

CREATE INDEX IF NOT EXISTS student_outcomes_report_idx
  ON student_outcomes (college_id, batch_year, kind);
CREATE INDEX IF NOT EXISTS student_outcomes_branch_idx
  ON student_outcomes (college_id, branch_id, batch_year);
CREATE INDEX IF NOT EXISTS student_outcomes_student_idx
  ON student_outcomes (student_id);

ALTER TABLE student_outcomes ENABLE ROW LEVEL SECURITY;
ALTER TABLE student_outcomes FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS t_student_outcomes ON student_outcomes;

-- Same shape as t_students (01-schema.sql): college for admin, branch for a
-- CR, own row for a student. A student can see and self-report their own
-- outcome; they must not see anyone else's salary.
CREATE POLICY t_student_outcomes ON student_outcomes
  USING (
        app_role() = 'owner'
     OR (college_id = app_college() AND app_role() = 'admin')
     OR (college_id = app_college() AND app_role() = 'sub_admin'
         AND branch_id = app_branch())
     OR (college_id = app_college() AND app_role() IN ('student','alumni')
         AND student_id IN (SELECT id FROM students WHERE user_id = app_user()))
  )
  WITH CHECK (
        app_role() = 'owner'
     OR (college_id = app_college() AND app_role() = 'admin')
     OR (college_id = app_college() AND app_role() = 'sub_admin'
         AND branch_id = app_branch())
     -- A student may write their own outcome, but never mark it verified.
     -- Verification is the placement cell's signature; the API enforces the
     -- `verified` flag separately, this is the backstop on identity.
     OR (college_id = app_college() AND app_role() IN ('student','alumni')
         AND student_id IN (SELECT id FROM students WHERE user_id = app_user()))
  );


-- ---------------------------------------------------------------------------
-- 2. outcome_documents — the evidence an assessor asks to see.
--
--    bytea, exactly like resumes (0004) and drive_attachments (0010). Same
--    reasoning: the file must be governed by the same RLS as the row it proves,
--    and an object store adds a second place for a tenant boundary to be got
--    wrong. NAAC 5.2.2 and 5.2.3 both require per-student artefacts, so this is
--    not optional decoration.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS outcome_documents (
  id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  college_id   bigint NOT NULL REFERENCES colleges(id) ON DELETE CASCADE,
  outcome_id   bigint NOT NULL REFERENCES student_outcomes(id) ON DELETE CASCADE,
  kind         text NOT NULL DEFAULT 'proof'
               CHECK (kind IN ('offer_letter','admission_letter','certificate',
                               'registration','proof','other')),
  filename     text NOT NULL,
  mime         text NOT NULL,
  byte_size    int  NOT NULL,
  data         bytea NOT NULL,
  uploaded_by  bigint REFERENCES users(id) ON DELETE SET NULL,
  created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS outcome_documents_outcome_idx
  ON outcome_documents (college_id, outcome_id);

ALTER TABLE outcome_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE outcome_documents FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS t_outcome_documents ON outcome_documents;

-- Visibility follows the outcome it belongs to. Written as an EXISTS against
-- student_outcomes so there is exactly one definition of who may see an
-- outcome, and this table cannot drift from it.
CREATE POLICY t_outcome_documents ON outcome_documents
  USING (
        app_role() = 'owner'
     OR (college_id = app_college()
         AND EXISTS (SELECT 1 FROM student_outcomes o WHERE o.id = outcome_id))
  )
  WITH CHECK (
        app_role() = 'owner'
     OR (college_id = app_college()
         AND EXISTS (SELECT 1 FROM student_outcomes o WHERE o.id = outcome_id))
  );


-- ---------------------------------------------------------------------------
-- 3. offers — give it a lifecycle and a real salary.
--
--    `offers` was (college_id, student_id, company_id, category): enough to say
--    an offer happened, not enough to say what happened to it. Revocations and
--    deferred joining dates were widespread in 2024-26; a college that reports
--    offers as placements will be reporting numbers it cannot defend.
--
--    Existing rows are backfilled to 'accepted', which is what the old boolean
--    meant in practice.
-- ---------------------------------------------------------------------------
ALTER TABLE offers ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'accepted';
ALTER TABLE offers ADD COLUMN IF NOT EXISTS annual_ctc numeric(12,2);
ALTER TABLE offers ADD COLUMN IF NOT EXISTS offered_at timestamptz;
ALTER TABLE offers ADD COLUMN IF NOT EXISTS decided_at timestamptz;
ALTER TABLE offers ADD COLUMN IF NOT EXISTS joining_date date;
ALTER TABLE offers ADD COLUMN IF NOT EXISTS revoked_at timestamptz;
ALTER TABLE offers ADD COLUMN IF NOT EXISTS revoke_reason text;
ALTER TABLE offers ADD COLUMN IF NOT EXISTS batch_year int;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'offers_status_check'
  ) THEN
    ALTER TABLE offers ADD CONSTRAINT offers_status_check
      CHECK (status IN ('offered','accepted','declined','revoked','deferred','joined'));
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS offers_batch_idx ON offers (college_id, batch_year, status);


-- ---------------------------------------------------------------------------
-- 4. Backfill.
--
--    Existing placements become primary 'placed_campus' outcomes so the first
--    report a college runs is not empty. Derived rows are marked source =
--    'derived' and verified = false: they are inferred from application status,
--    not confirmed by anyone, and an assessor is entitled to know the
--    difference. ON CONFLICT DO NOTHING keeps this migration re-runnable.
-- ---------------------------------------------------------------------------
-- A migration runs with NO tenant context, so app_role() is NULL. `students`
-- and `applications` are under FORCE ROW LEVEL SECURITY, whose policies all
-- require a role — so a plain backfill SELECT here matches ZERO rows and the
-- INSERT silently writes nothing. No error, no warning: the migration
-- "succeeds", the college's first report reads zero placements, and nobody
-- finds out until an assessor asks. (Observed: 50 placed applications, INSERT
-- 0 0.) The fix is to establish an owner scope for the duration of the
-- backfill, exactly as tenant_connection() does per request.
--
-- set_config(..., is_local => true) scopes the setting to this transaction, so
-- it cannot leak into whatever runs next on this connection.
DO $backfill$
DECLARE
  n_outcomes int;
  n_offers   int;
BEGIN
  PERFORM set_config('app.role', 'owner', true);

  INSERT INTO student_outcomes
    (college_id, branch_id, student_id, batch_year, kind, is_primary,
     company_id, source, verified, created_at)
  SELECT DISTINCT ON (a.student_id)
         a.college_id, a.branch_id, a.student_id, s.batch_year,
         'placed_campus', true, a.company_id, 'derived', false, now()
  FROM applications a
  JOIN students s ON s.id = a.student_id
  WHERE a.status = 'placed'
    AND NOT EXISTS (
      SELECT 1 FROM student_outcomes o
       WHERE o.student_id = a.student_id AND o.is_primary
    )
  ORDER BY a.student_id, a.id;
  GET DIAGNOSTICS n_outcomes = ROW_COUNT;

  UPDATE offers o SET batch_year = s.batch_year
  FROM students s WHERE s.id = o.student_id AND o.batch_year IS NULL;
  GET DIAGNOSTICS n_offers = ROW_COUNT;

  -- Say the numbers out loud. The failure mode above was silent, and a
  -- migration that reports "0 backfilled" when a college has placements is a
  -- signal somebody can act on.
  RAISE NOTICE '0011 backfill: % placement outcome(s), % offer(s) dated', n_outcomes, n_offers;
END
$backfill$;


-- ---------------------------------------------------------------------------
-- 5. Grants. The runner writes schema_migrations, not this file.
-- ---------------------------------------------------------------------------
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_user') THEN
    GRANT SELECT, INSERT, UPDATE, DELETE ON student_outcomes   TO app_user;
    GRANT SELECT, INSERT, UPDATE, DELETE ON outcome_documents  TO app_user;
    GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public      TO app_user;
  END IF;
END $$;
