from fastapi import APIRouter, Depends
from sqlalchemy import text

from ..auth import Claims, get_claims
from ..db import tenant_connection
from ..permissions import require_staff

router = APIRouter(prefix="/api", tags=["companies"])


@router.get("/companies")
def list_companies(claims: Claims = Depends(get_claims)):
    """The drive list for the placement cell — drafts included, on purpose.

    Staff only. This had no role check at all, so any authenticated account
    could call it, and the RLS policy on companies is
    `app_role() = 'owner' OR college_id = app_college()` — tenant-scoped with
    no condition on status. A student with a valid token could therefore list
    every drive in their college including unpublished drafts, with package
    figures and registration counts.

    That is the same leak as SECURITY_REVIEW F-2. The fix for F-2 added
    `WHERE status = 1` to the student's own endpoint in portal.py; this route
    was serving the same table and was missed. Rather than filter by status
    here, the guard is the correct fix: this endpoint exists precisely so the
    placement cell can see drafts. Students have /api/me/drives, which filters
    status and deadline and adds their eligibility verdict.
    """
    require_staff(claims)
    with tenant_connection(claims) as conn:
        rows = conn.execute(text("""
            SELECT c.id, c.name, c.category, c.package, c.status,
                   c.eligible_branches, c.deadline, c.role_title,
                   (SELECT count(*) FROM applications a WHERE a.company_id = c.id) AS registered,
                   (SELECT count(*) FROM applications a
                     WHERE a.company_id = c.id AND a.status='placed')             AS placed
            FROM companies c
            ORDER BY c.package DESC NULLS LAST
        """)).mappings().all()
    return [dict(r) for r in rows]
