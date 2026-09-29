-- Migration 0012: repair the seeds that 0009 silently failed to write.
--
-- Additive and idempotent. Apply after 0011.
--
-- ===========================================================================
-- WHAT WENT WRONG
--
-- 0009 seeds default buckets and export templates for every existing college:
--
--     INSERT INTO buckets (...) SELECT c.id, ... FROM colleges c WHERE ...
--     INSERT INTO export_templates (...) SELECT c.id, ... FROM colleges c ...
--
-- `colleges` is under FORCE ROW LEVEL SECURITY with
--
--     CREATE POLICY t_colleges ON colleges
--       USING (app_role() = 'owner' OR id = app_college());
--
-- A migration runs with no tenant context, so app_role() is NULL, the policy
-- matches nothing, and `FROM colleges` returns zero rows. All three INSERTs
-- wrote nothing. No error, no warning — the migration reported success.
--
-- Reproduced: two colleges present before 0009, `FROM colleges` visible as
-- owner = 2 and with no context = 0, buckets seeded = 0, templates = 0.
--
-- This is the identical failure that 0011's backfill had (found and fixed
-- there). A sweep of 0002-0010 found no other instance: these three statements
-- and 0011's two were the only data-modifying statements in any migration that
-- read from an RLS-protected table.
--
-- IMPACT, stated honestly: moderate, not urgent. Buckets define what Tier 1,
-- Dream and the rest mean for display and for the drive list's category label,
-- which joins LEFT so it degrades to a null label rather than breaking.
-- eligibility.py does NOT reference buckets, so the one-offer-and-out policy
-- was never affected and no figure was ever miscalculated. What colleges
-- actually got was an empty Buckets screen and no export presets, where they
-- should have had five buckets and two templates, with officers able to create
-- them by hand.
--
-- THE LESSON, which matters more than this fix: any migration that writes rows
-- derived from a SELECT over an RLS-protected table must establish a tenant
-- scope first, and should report its row count so that silence is not mistaken
-- for success.
-- ===========================================================================

DO $repair$
DECLARE
  n_colleges  int;
  n_buckets   int;
  n_templates int;
BEGIN
  -- set_config(..., is_local => true) scopes this to the transaction, so it
  -- cannot leak onto whatever runs next on this connection. Same mechanism
  -- tenant_connection() uses per request.
  PERFORM set_config('app.role', 'owner', true);

  SELECT count(*) INTO n_colleges FROM colleges;

  INSERT INTO buckets (college_id, key, label, min_package, max_package,
                       counts_toward_cap, ignores_cap, sort_order)
  SELECT c.id, v.key, v.label, v.minp, v.maxp, v.cap, v.ign, v.ord
  FROM colleges c
  CROSS JOIN (VALUES
    ('tier1',      'Tier 1',     2000000::numeric, NULL::numeric,    true,  false, 1),
    ('tier2',      'Tier 2',      800000::numeric, 1500000::numeric, true,  false, 2),
    ('dream',      'Dream',      1500000::numeric, NULL::numeric,    false, true,  3),
    ('core',       'Core',           NULL::numeric, 1000000::numeric, true,  false, 4),
    ('internship', 'Internship',     NULL::numeric, NULL::numeric,    false, true,  5)
  ) AS v(key, label, minp, maxp, cap, ign, ord)
  -- Per (college, key), not per college: a college that hand-created one
  -- bucket after noticing the screen was empty still gets the other four,
  -- and nothing already there is duplicated or overwritten.
  WHERE NOT EXISTS (
    SELECT 1 FROM buckets b WHERE b.college_id = c.id AND b.key = v.key
  )
  ON CONFLICT DO NOTHING;
  GET DIAGNOSTICS n_buckets = ROW_COUNT;

  INSERT INTO export_templates (college_id, name, columns, is_default)
  SELECT c.id, t.name, t.cols, t.dflt
  FROM colleges c
  CROSS JOIN (VALUES
    ('Short info',
     '["roll_no","full_name","branch","email","cgpa"]'::jsonb, true),
    ('Full info',
     '["roll_no","full_name","branch","email","cgpa","backlogs","tenth_pct","twelfth_pct","current_round","status","applied_at"]'::jsonb, false)
  ) AS t(name, cols, dflt)
  WHERE NOT EXISTS (
    SELECT 1 FROM export_templates e
     WHERE e.college_id = c.id AND e.name = t.name
  )
  ON CONFLICT DO NOTHING;
  GET DIAGNOSTICS n_templates = ROW_COUNT;

  RAISE NOTICE '0012 repair: % college(s) -> % bucket(s), % export template(s) created',
               n_colleges, n_buckets, n_templates;

  IF n_colleges > 0 AND n_buckets = 0 AND n_templates = 0 THEN
    RAISE NOTICE '0012: nothing to repair — seeds were already present.';
  END IF;
END
$repair$;
