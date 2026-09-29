from fastapi import APIRouter, Depends
from sqlalchemy import text

from ..auth import Claims, get_claims
from ..db import tenant_connection
from ..outcomes import count_batch, recent_batches
from ..permissions import require_cr_capability
from ..reports import naac_5_2_1, naac_5_2_2, nba_4_6_index

router = APIRouter(prefix="/api", tags=["dashboard"])

# the pipeline order used to build the funnel
ROUNDS = [
    "resume_screening", "online_assessment", "technical_1", "technical_2",
    "technical_3", "managerial", "hr", "final_placement",
]


@router.get("/dashboard/stats")
def dashboard_stats(batch_year: int | None = None,
                    claims: Claims = Depends(get_claims)):
    """Everything here is tenant-scoped by RLS — the same code serves every
    college, and each caller only ever sees their own rows.

    The headline number used to be

        placement_rate = placed_applications / total_applications

    which is not a placement rate under any definition anyone uses. A batch of
    100 students who each register for 5 drives generates 500 applications; if
    50 of those students are placed, that formula reports 10%. Verified against
    a seeded database: it reported 10.0% for a batch that placed 50%.

    Worse, it under-reported MORE the harder students worked, because every
    extra application grew the denominator. The number moved in the opposite
    direction to the thing it claimed to measure.

    Counting now goes through outcomes.count_batch(), the same function the
    accreditation reports use, so the dashboard and a NAAC submission can never
    disagree about how many students were placed.
    """
    require_cr_capability(claims, "view_branch_dashboard")

    # A CR's dashboard is their branch. RLS already confines their rows, but
    # count_batch's optional branch filter also needs to match, or the
    # denominator (students) would be branch-scoped by RLS while the officer's
    # view is not — same query, different meaning, depending on who calls it.
    branch = claims.branch_id if claims.role == "sub_admin" else None

    with tenant_connection(claims) as conn:
        if batch_year is None:
            recent = recent_batches(conn, 1, branch)
            batch_year = recent[0] if recent else None

        c = count_batch(conn, batch_year, branch) if batch_year else None

        totals = conn.execute(text("""
            SELECT
              (SELECT count(*) FROM students)                              AS students,
              (SELECT count(*) FROM companies)                             AS companies,
              (SELECT count(*) FROM applications)                          AS applications,
              (SELECT count(*) FROM applications WHERE status='active')    AS active,
              (SELECT count(*) FROM applications WHERE status='rejected')  AS rejected,
              (SELECT count(*) FROM applications WHERE status='placed')    AS placed_applications
        """)).mappings().one()

        by_round = dict(conn.execute(text(
            "SELECT current_round, count(*) FROM applications GROUP BY current_round"
        )).all())

    if c is None:
        # No batch years on the roster yet. Say so rather than reporting 0%,
        # which reads as "nobody was placed" when it means "nothing is recorded".
        return {
            "totals": dict(totals),
            "batch_year": None,
            "placement_rate": None,
            "needs_batch_years": True,
            "message": ("No graduating batch is on record. Import a roster with a "
                        "batch_year column to get placement figures."),
            "funnel": [{"round": r, "count": by_round.get(r, 0)} for r in ROUNDS],
            "scope": "branch" if claims.role == "sub_admin" else "college",
        }

    return {
        "totals": dict(totals),
        "batch_year": batch_year,
        "batch": {
            "final_year_students": c.final_year,
            "placed": c.placed,
            "higher_studies": c.higher_studies,
            "entrepreneurship": c.entrepreneurship,
            "exam_qualified": c.exam_qualified,
            "not_placed": c.not_placed,
            "unavailable": c.unavailable,
            "unrecorded": c.unrecorded,
        },
        # placed students over final-year students: the number people say aloud
        "placement_rate": round((c.placed / c.final_year) * 100, 1) if c.final_year else 0.0,
        "accreditation": {
            "naac_5_2_1": naac_5_2_1(final_year=c.final_year, placed=c.placed,
                                     higher_studies=c.higher_studies),
            "naac_5_2_2": naac_5_2_2(final_year=c.final_year,
                                     higher_studies=c.higher_studies),
            "nba_4_6_index": nba_4_6_index(final_year=c.final_year, placed=c.placed,
                                           higher_studies=c.higher_studies,
                                           entrepreneurship=c.entrepreneurship),
        },
        # Surfaced on the dashboard rather than buried in a report, because an
        # officer looking at a placement rate needs to know what share of the
        # batch it is actually based on. At 60% coverage every figure above
        # understates the college, and that is fixable by chasing outcomes.
        "data_quality": {
            "coverage_pct": round(((c.final_year - c.unrecorded) / c.final_year) * 100, 1)
                            if c.final_year else 0.0,
            "unrecorded": c.unrecorded,
            "complete": c.unrecorded == 0,
        },
        "funnel": [{"round": r, "count": by_round.get(r, 0)} for r in ROUNDS],
        "scope": "branch" if claims.role == "sub_admin" else "college",
    }
