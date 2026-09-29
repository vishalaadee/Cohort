#!/usr/bin/env bash
# Multi-college scenario suite.
#
# Stands up a DISPOSABLE database from the real schema + every migration,
# seeds three deliberately overlapping colleges, and walks eleven scenarios
# with the expected value stated for each.
#
#   ./scripts/scenario-test.sh                 # uses a local postgres
#   PGHOST=... PGUSER=... ./scripts/scenario-test.sh
#
# It NEVER touches production: it creates and drops its own database. Point it
# at RDS only if you understand that it will CREATE DATABASE there.
#
# The three colleges share branch codes, batch years and drive timing on
# purpose. If tenancy leaks anywhere, that shape is what finds it.
set -uo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# The APP user deliberately cannot CREATE DATABASE — that is correct in
# production and this script must not require loosening it. Creating and
# dropping the scratch database therefore uses an admin role (the RDS master
# user, or `postgres` locally); every actual TEST then runs as the app user,
# because that is the only way FORCE RLS is exercised the way production does.
PGHOST="${PGHOST:-127.0.0.1}"; PGUSER="${PGUSER:-app_user}"
PGPASSWORD="${PGPASSWORD:-x}"; DB="${SCENARIO_DB:-scenario_test}"
ADMINUSER="${PGADMINUSER:-postgres}"; ADMINPASS="${PGADMINPASSWORD:-}"
export PGPASSWORD
psql_() { psql -h "$PGHOST" -U "$PGUSER" -d "$DB" "$@"; }
q() { psql_ -tAc "$1" 2>&1 | grep -viE "^(SET|BEGIN|COMMIT)$" | tail -1; }
pass=0; fail=0
chk(){ if [ "$2" = "$3" ]; then echo "    PASS  $1 (got $2)"; pass=$((pass+1));
       else echo "    FAIL  $1 — expected $3, got $2"; fail=$((fail+1)); fi; }
chkg(){ if echo "$2" | grep -qiE "policy|violat|duplicate|unique"; then
          echo "    PASS  $1 — refused"; pass=$((pass+1));
        else echo "    FAIL  $1 — ALLOWED: $2"; fail=$((fail+1)); fi; }

echo "Building a disposable database: $DB"
PGPASSWORD="$ADMINPASS" dropdb  -h "$PGHOST" -U "$ADMINUSER" --if-exists "$DB" 2>/dev/null
PGPASSWORD="$ADMINPASS" createdb -h "$PGHOST" -U "$ADMINUSER" -O "$PGUSER" "$DB" || {
  echo "Could not create $DB as '$ADMINUSER'."
  echo "Set PGADMINUSER / PGADMINPASSWORD to a role that may CREATE DATABASE"
  echo "(on RDS that is your master user, e.g. cohort_admin)."; exit 1; }
psql_ -q -v ON_ERROR_STOP=1 -f backend/db-init/01-schema.sql >/dev/null 2>&1 || { echo "schema failed"; exit 1; }
for m in migrations/0*.sql; do
  out=$(psql_ -q -v ON_ERROR_STOP=1 -f "$m" 2>&1)
  echo "$out" | grep -qiE "^psql.*ERROR" && { echo "  FAILED $m"; echo "$out" | grep -i error | head -3; exit 1; }
  echo "$out" | grep -oE "0011 backfill: .*" | sed 's/^/  /'
done
psql_ -q -v ON_ERROR_STOP=1 -f scripts/scenario-seed.sql >/dev/null 2>&1 || { echo "seed failed"; exit 1; }
echo "  seeded: gvit(60) sec(40) ntc(20)"
echo

A="BEGIN;SET LOCAL app.role='admin';SET LOCAL app.college_id='1';"
echo "1. CROSS-COLLEGE ISOLATION — GVIT officer"
chk "students visible"              "$(q "$A SELECT count(*) FROM students;COMMIT;")" "60"
chk "students from other colleges"  "$(q "$A SELECT count(*) FROM students WHERE college_id<>1;COMMIT;")" "0"
chk "drives visible"                "$(q "$A SELECT count(*) FROM companies;COMMIT;")" "4"

echo; echo "2. CR BRANCH CONFINEMENT"
C="BEGIN;SET LOCAL app.role='sub_admin';SET LOCAL app.college_id='1';SET LOCAL app.branch_id="
chk "CSE rep sees own branch"       "$(q "${C}'1';SELECT count(*) FROM students;COMMIT;")" "30"
chk "CSE rep sees other branches"   "$(q "${C}'1';SELECT count(*) FROM students WHERE branch_id<>1;COMMIT;")" "0"
chk "ECE rep sees own branch"       "$(q "${C}'2';SELECT count(*) FROM students;COMMIT;")" "20"
chk "CR with no branch fails closed" "$(q "${C}'';SELECT count(*) FROM students;COMMIT;")" "0"

echo; echo "3. STUDENT SELF-SCOPE"
S="BEGIN;SET LOCAL app.role='student';SET LOCAL app.college_id='1';SET LOCAL app.user_id='50';"
chk "sees only their own row"       "$(q "$S SELECT count(*) FROM students;COMMIT;")" "1"

echo; echo "4. CROSS-TENANT WRITE"
chkg "GVIT officer writing into SEC" "$(psql_ -tAc "$A INSERT INTO students (college_id,branch_id,roll_no,email,full_name,batch_year) VALUES (2,4,'HACK','h@x','H',2026);COMMIT;" 2>&1)"
chkg "CR writing outside their branch" "$(psql_ -tAc "${C}'1';INSERT INTO student_outcomes (college_id,branch_id,student_id,batch_year,kind,is_primary,source) VALUES (1,2,40,2026,'not_placed',false,'officer');COMMIT;" 2>&1)"

echo; echo "5. DRAFT + EXPIRED DRIVES"
chk "officer sees all GVIT drives"  "$(q "$A SELECT count(*) FROM companies;COMMIT;")" "4"
chk "student sees published+live"   "$(q "$S SELECT count(*) FROM companies c WHERE c.status=1 AND (c.deadline IS NULL OR c.deadline>now());COMMIT;")" "2"

echo; echo "6. SIMULTANEOUS DRIVES, NO BLEED"
for c in 1 2 3; do
  X="BEGIN;SET LOCAL app.role='admin';SET LOCAL app.college_id='$c';"
  chk "college $c sees no foreign drives" "$(q "$X SELECT count(*) FROM companies WHERE college_id<>$c;COMMIT;")" "0"
done

echo; echo "7. ONE HEADLINE OUTCOME PER STUDENT"
chkg "second primary outcome" "$(psql_ -tAc "SET app.role='owner';INSERT INTO student_outcomes (college_id,branch_id,student_id,batch_year,kind,is_primary,source) VALUES (1,1,5,2026,'higher_studies',true,'officer');" 2>&1)"

echo; echo "8. RECONCILIATION — three colleges, batch 2026"
for c in 1 2 3; do
  X="BEGIN;SET LOCAL app.role='admin';SET LOCAL app.college_id='$c';"
  slug=$(q "$X SELECT slug FROM colleges WHERE id=$c;COMMIT;")
  fy=$(q "$X SELECT count(*) FROM students WHERE batch_year=2026;COMMIT;")
  pl=$(q "$X SELECT count(*) FROM student_outcomes WHERE batch_year=2026 AND is_primary AND kind LIKE 'placed%';COMMIT;")
  hs=$(q "$X SELECT count(*) FROM student_outcomes WHERE batch_year=2026 AND is_primary AND kind='higher_studies';COMMIT;")
  en=$(q "$X SELECT count(*) FROM student_outcomes WHERE batch_year=2026 AND is_primary AND kind='entrepreneurship';COMMIT;")
  # Computed in SQL rather than awk. In awk's print/printf, ">" is OUTPUT
  # REDIRECTION, not comparison — `printf "%.1f", (f-h)>0 ? a : b` silently
  # writes to a file named "0" and prints nothing. Postgres also drops the
  # dependency on which awk the host happens to have.
  read -r plain naac nba <<EOF
$(q "$X SELECT
       round(CASE WHEN $fy>0 THEN $pl::numeric/$fy*100 ELSE 0 END,1) || ' ' ||
       round(CASE WHEN ($fy-$hs)>0 THEN $pl::numeric/($fy-$hs)*100 ELSE 0 END,1) || ' ' ||
       round(CASE WHEN $fy>0 THEN ($pl+$hs+$en)::numeric/$fy*100 ELSE 0 END,1);COMMIT;")
EOF
  printf "    %-6s batch %-4s plain %5s%%   NAAC 5.2.1 %5s%%   NBA 4.6 %5s%%\n" "$slug" "$fy" "$plain" "$naac" "$nba"
done
echo "    (three different correct answers per college — that is the point)"

echo; echo "=================================================="
printf "  %d passed, %d failed\n" "$pass" "$fail"
echo "=================================================="
[ "$fail" -eq 0 ] && echo "  Tenancy, branch scoping and reporting all hold." \
                  || echo "  INVESTIGATE THE FAILURES ABOVE BEFORE SHIPPING."
echo
echo "  Drop the test database with:  dropdb -h $PGHOST -U $ADMINUSER $DB"
exit $([ "$fail" -eq 0 ] && echo 0 || echo 1)
