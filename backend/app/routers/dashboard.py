from fastapi import APIRouter, Depends
from sqlalchemy import text

from ..auth import Claims, get_claims
from ..db import tenant_connection

router = APIRouter(prefix="/api", tags=["dashboard"])

# the pipeline order used to build the funnel
ROUNDS = [
    "resume_screening", "online_assessment", "technical_1", "technical_2",
    "technical_3", "managerial", "hr", "final_placement",
]


@router.get("/dashboard/stats")
def dashboard_stats(claims: Claims = Depends(get_claims)):
    """Everything here is tenant-scoped by RLS — the same code serves every
    college, and each caller only ever sees their own rows."""
    with tenant_connection(claims) as conn:
        totals = conn.execute(text("""
            SELECT
              (SELECT count(*) FROM students)                              AS students,
              (SELECT count(*) FROM companies)                             AS companies,
              (SELECT count(*) FROM applications)                          AS applications,
              (SELECT count(*) FROM applications WHERE status='active')    AS active,
              (SELECT count(*) FROM applications WHERE status='placed')    AS placed,
              (SELECT count(*) FROM applications WHERE status='rejected')  AS rejected
        """)).mappings().one()

        by_round = dict(
            conn.execute(text(
                "SELECT current_round, count(*) FROM applications GROUP BY current_round"
            )).all()
        )

    apps = totals["applications"] or 0
    placement_rate = round((totals["placed"] / apps) * 100, 1) if apps else 0.0
    return {
        "totals": dict(totals),
        "placement_rate": placement_rate,
        "funnel": [{"round": r, "count": by_round.get(r, 0)} for r in ROUNDS],
    }
