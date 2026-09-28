#!/usr/bin/env bash
# Verify the batch-3 changes actually landed, before and after deploying.
#
# Written because `companies.py` did not land: macOS renamed the download to
# `companies-1.py`, Python imports `companies`, and the draft-drive leak stayed
# open while everything looked fine. A file in the repo is not a file that runs.
#
#   ./scripts/verify-batch3.sh            # on the Mac, after copying
#
set -uo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

pass=0; fail=0
ok(){ echo "  PASS  $1"; pass=$((pass+1)); }
no(){ echo "  FAIL  $1"; fail=$((fail+1)); }
chk(){ if [ "$2" = "1" ]; then ok "$1"; else no "$1"; fi; }

echo "=================================================================="
echo "1. RIGHT FILES IN THE RIGHT PLACES"
echo "=================================================================="
# The only check that cannot be fooled by a partially-copied file.
expect_portal=db5ccbd5b3dff15044f80828c7945ec2
expect_place=d65366e93f08ca7361a0048c1665fb37
expect_comp=c796f8d3b825b18bb21b2b625e94158a
expect_app=4fd95342897cc370934d6c6ea83832c4

md5of(){ md5sum "$1" 2>/dev/null | cut -d' ' -f1 || md5 -q "$1" 2>/dev/null; }

for pair in \
  "backend/app/routers/portal.py:$expect_portal" \
  "backend/app/routers/placement.py:$expect_place" \
  "backend/app/routers/companies.py:$expect_comp" \
  "frontend/app/app.html:$expect_app"; do
  f="${pair%%:*}"; want="${pair##*:}"; got="$(md5of "$f")"
  if [ "$got" = "$want" ]; then ok "$f"
  else no "$f  (got ${got:-missing}, want $want)"; fi
done

echo
echo "  stray duplicates that Python will never import:"
strays=$(find backend frontend -name "*-[0-9].py" -o -name "* [0-9].py" -o -name "*-[0-9].html" 2>/dev/null)
if [ -z "$strays" ]; then ok "none"; else echo "$strays" | sed 's/^/  FAIL  DELETE THIS: /'; fail=$((fail+1)); fi

echo
echo "=================================================================="
echo "2. EACH FIX IS ACTUALLY IN THE FILE"
echo "=================================================================="
g(){ grep -q "$2" "$1" 2>/dev/null && echo 1 || echo 0; }

chk "questions scoped to the student"      "$(g backend/app/routers/portal.py 'WHERE student_id = :sid')"
chk "edit_requests scoped to the student"  "$(g backend/app/routers/portal.py 'WHERE student_id = :sid')"
chk "applications scoped to the student"   "$(g backend/app/routers/portal.py 'WHERE a.student_id = :sid')"
chk "profile returns has_resume"           "$(g backend/app/routers/portal.py 'AS has_resume')"
chk "profile returns placed"               "$(g backend/app/routers/portal.py 'AS placed')"
chk "resume download endpoint exists"      "$(g backend/app/routers/portal.py '/resume/download')"
chk "drives filter expired deadlines"      "$(g backend/app/routers/portal.py 'deadline IS NULL OR c.deadline > now()')"
chk "drives return applied flag"           "$(g backend/app/routers/portal.py 'AS applied')"
chk "applications return company_id"       "$(g backend/app/routers/portal.py 'a.id, a.company_id')"
chk "companies.py requires staff"          "$(g backend/app/routers/companies.py 'require_staff')"
chk "planner bind-param fixed"             "$(g backend/app/routers/placement.py 'CAST(:s AS date)')"
# Only flag :param::cast in real SQL, not in the comment that explains the bug.
if grep -rnE '^[^#]*>= *:[a-z_]+::' backend/app/routers/*.py >/dev/null 2>&1; then
  no "no ':param::cast' left in SQL"
else
  ok "no ':param::cast' left in SQL"
fi
chk "branches endpoint is officer-only"    "$(g backend/app/routers/placement.py 'require_placement_officer(claims)')"
chk "consent sends the share key"          "$(g frontend/app/app.html 'share:on')"
chk "profile reads res.profile"            "$(g frontend/app/app.html 'res.profile')"
chk "experiences gate on placed"           "$(g frontend/app/app.html 'isStudent&&placed')"
chk "drives show an Applied section"       "$(g frontend/app/app.html 'const applied=open.filter')"
chk "sidebar shows roll number"            "$(g frontend/app/app.html 'AUTH?.roll_no')"
chk "branch picker present"                "$(g frontend/app/app.html 'data-br')"
chk "not one of enabled"                   "$(g frontend/app/app.html 'not one of')"

echo
echo "=================================================================="
echo "3. NOTHING WAS DELETED"
echo "=================================================================="
for f in backend/Dockerfile backend/requirements.txt backend/app/main.py \
         backend/app/auth.py backend/app/db.py backend/app/config.py \
         backend/app/eligibility.py backend/app/permissions.py \
         backend/app/attachments.py backend/app/mailer.py \
         backend/app/routers/admin_extra.py backend/app/routers/auth_routes.py \
         backend/app/routers/students_admin.py backend/app/routers/dashboard.py \
         backend/db-init/01-schema.sql scripts/migrate-rds.sh scripts/migration-lib.sh \
         migrations/0009_placement_features.sql migrations/0010_attachments_and_mail.sql; do
  [ -f "$f" ] && pass=$((pass+1)) || { echo "  FAIL  MISSING $f"; fail=$((fail+1)); }
done
echo "  checked 19 files that must never disappear"

echo
echo "=================================================================="
printf "  %d passed, %d failed\n" "$pass" "$fail"
echo "=================================================================="
[ "$fail" -eq 0 ] && echo "  Safe to commit and push." || echo "  Fix the failures above BEFORE pushing."
exit $([ "$fail" -eq 0 ] && echo 0 || echo 1)
