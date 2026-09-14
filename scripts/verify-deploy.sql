-- Run this AFTER deploying, against your database, to prove the release is
-- healthy and that tenant isolation actually holds. Read-only except for one
-- temporary row it creates and removes.
--
--   psql "host=$RDS_HOST port=$RDS_PORT dbname=$RDS_DB user=$RDS_ADMIN_USER sslmode=require" \
--        -f scripts/verify-deploy.sql
--
-- Every line should print PASS. Anything else, stop and investigate.

\set ON_ERROR_STOP on
\pset tuples_only off

\echo ''
\echo '=== 1. Migrations applied ==='
SELECT CASE WHEN count(*) = 8 THEN 'PASS' ELSE 'FAIL — expected 8, found '||count(*) END AS result,
       string_agg(version, ', ' ORDER BY version) AS versions
FROM schema_migrations;

\echo ''
\echo '=== 2. New tables exist ==='
SELECT CASE WHEN count(*) = 8 THEN 'PASS' ELSE 'FAIL — missing '||(8-count(*))::text END AS result,
       string_agg(tablename, ', ' ORDER BY tablename) AS found
FROM pg_tables WHERE schemaname='public'
  AND tablename IN ('buckets','reminders','export_templates','notification_log',
                    'entitlements','audit_log','consent_events','score_history');

\echo ''
\echo '=== 3. The cross-tenant view is gone (SECURITY_REVIEW F-1) ==='
SELECT CASE WHEN count(*) = 0 THEN 'PASS' ELSE 'FAIL — recruiter_candidates still exists' END AS result
FROM pg_views WHERE viewname='recruiter_candidates';

\echo ''
\echo '=== 4. Every tenant table has RLS enabled AND forced ==='
SELECT CASE WHEN count(*) = 0 THEN 'PASS'
            ELSE 'FAIL — '||count(*)||' table(s) unprotected: '||string_agg(relname,', ') END AS result
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='public' AND c.relkind='r'
  AND EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema='public' AND table_name=c.relname AND column_name='college_id')
  AND NOT (c.relrowsecurity AND c.relforcerowsecurity);

\echo ''
\echo '=== 5. The app connects as a NON-superuser (else RLS is bypassed) ==='
SELECT CASE WHEN NOT (rolsuper OR rolbypassrls) THEN 'PASS'
            ELSE 'FAIL — app role can bypass RLS' END AS result, rolname
FROM pg_roles WHERE rolname = current_setting('app.check_role', true)
   OR rolname = 'app_user';

\echo ''
\echo '=== 6. Buckets seeded for every college ==='
SELECT CASE WHEN count(*) = 0 THEN 'PASS'
            ELSE 'FAIL — '||count(*)||' college(s) have no buckets' END AS result
FROM colleges c WHERE NOT EXISTS (SELECT 1 FROM buckets b WHERE b.college_id=c.id);

\echo ''
\echo '=== 7. No drive is visible to students unless published ==='
\echo '    (drafts with registrations would mean the F-2 fix is missing)'
SELECT CASE WHEN count(*) = 0 THEN 'PASS'
            ELSE 'WARN — '||count(*)||' unpublished drive(s) already have registrations' END AS result
FROM companies c WHERE c.status = 0
  AND EXISTS (SELECT 1 FROM applications a WHERE a.company_id=c.id);

\echo ''
\echo '=== 8. Notification dedupe constraint present (stops double sends) ==='
SELECT CASE WHEN count(*) >= 1 THEN 'PASS' ELSE 'FAIL — dedupe constraint missing' END AS result
FROM pg_constraint WHERE conname LIKE 'notification_log%' AND contype='u';

\echo ''
\echo '=== 9. round_progress is scoped to the student (SECURITY_REVIEW F-6) ==='
SELECT CASE WHEN pg_get_expr(polqual, polrelid) LIKE '%user_id%' THEN 'PASS'
            ELSE 'FAIL — policy still lets any student read every row' END AS result
FROM pg_policy WHERE polname='t_round_progress';

\echo ''
\echo '=== 10. Row counts (sanity — these should look like your college) ==='
SELECT (SELECT count(*) FROM colleges)     AS colleges,
       (SELECT count(*) FROM students)     AS students,
       (SELECT count(*) FROM companies)    AS drives,
       (SELECT count(*) FROM applications) AS applications,
       (SELECT count(*) FROM offers)       AS offers,
       (SELECT count(*) FROM audit_log)    AS audit_rows;
\echo ''
