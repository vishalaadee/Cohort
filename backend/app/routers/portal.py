"""Student-facing endpoints beyond the shared dashboard/companies."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from ..auth import Claims, get_claims
from ..db import tenant_connection

router = APIRouter(prefix="/api/me", tags=["portal"])


@router.get("/applications")
def my_applications(claims: Claims = Depends(get_claims)):
    if claims.role != "student":
        raise HTTPException(403, "Student account required")
    # RLS limits the rows to the student's own applications automatically.
    with tenant_connection(claims) as conn:
        rows = conn.execute(text("""
            SELECT a.id, c.name AS company, c.category, c.package,
                   a.current_round, a.status, a.created_at
            FROM applications a JOIN companies c ON c.id = a.company_id
            ORDER BY a.created_at DESC
        """)).mappings().all()
    return [dict(r) for r in rows]
