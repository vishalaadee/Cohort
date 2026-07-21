from fastapi import APIRouter, Depends
from sqlalchemy import text

from ..auth import Claims, get_claims
from ..db import tenant_connection

router = APIRouter(prefix="/api", tags=["companies"])


@router.get("/companies")
def list_companies(claims: Claims = Depends(get_claims)):
    with tenant_connection(claims) as conn:
        rows = conn.execute(text("""
            SELECT c.id, c.name, c.category, c.package, c.status,
                   c.eligible_branches,
                   (SELECT count(*) FROM applications a WHERE a.company_id = c.id) AS registered,
                   (SELECT count(*) FROM applications a
                     WHERE a.company_id = c.id AND a.status='placed')             AS placed
            FROM companies c
            ORDER BY c.package DESC NULLS LAST
        """)).mappings().all()
    return [dict(r) for r in rows]
