"""Counting outcomes out of the database.

Deliberately separate from `reports.py`, which holds the accreditation
arithmetic and touches no database at all. The split is so the formulas stay
testable without Postgres and so there is exactly ONE definition of how a batch
is counted — the dashboard and the accreditation reports must never disagree
about how many students were placed, and the only way to guarantee that is for
both to call the same function.

Two counting rules that are easy to get wrong and expensive when you do:

  1. Placement is per DISTINCT STUDENT, never per application. The
     `student_outcomes_one_primary` partial unique index guarantees at most one
     headline outcome per student, so counting primary rows is already
     per-student. The dashboard this replaces counted placed APPLICATIONS over
     total applications and reported 10% for a batch that placed 50%.

  2. `competitive_exam` is NOT filtered on is_primary. A student can be placed
     AND have cleared GATE; NAAC counts those under 5.2.1 and 5.2.3
     respectively. Treating them as mutually exclusive loses one of them.
"""
from sqlalchemy import text

from .reports import BatchCounts

PLACED_KINDS = ("placed_campus", "placed_offcampus")


def count_batch(conn, batch_year: int, branch_id: int | None = None) -> BatchCounts:
    """Every number the frameworks need, for one batch, counted once.

    RLS does the tenant and branch confinement, so this carries no college
    filter — a CR calling it sees their branch because the policy says so, not
    because of anything here. `branch_id` is for an officer asking about one
    programme (NBA is assessed per programme), not for enforcement.
    """
    p = {"by": batch_year, "br": branch_id}
    bf = "AND branch_id = :br" if branch_id else ""

    final_year = conn.execute(text(f"""
        SELECT count(*) FROM students WHERE batch_year = :by {bf}
    """), p).scalar() or 0

    by_kind = {r[0]: r[1] for r in conn.execute(text(f"""
        SELECT kind, count(*) FROM student_outcomes
         WHERE batch_year = :by AND is_primary {bf}
         GROUP BY kind
    """), p).all()}

    exam = conn.execute(text(f"""
        SELECT count(DISTINCT student_id) FROM student_outcomes
         WHERE batch_year = :by AND kind = 'competitive_exam' {bf}
    """), p).scalar() or 0

    salaries = [float(r[0]) for r in conn.execute(text(f"""
        SELECT annual_ctc FROM student_outcomes
         WHERE batch_year = :by AND is_primary {bf}
           AND kind IN ('placed_campus','placed_offcampus')
           AND annual_ctc IS NOT NULL
    """), p).all()]

    with_outcome = sum(by_kind.values())
    return BatchCounts(
        batch_year=batch_year,
        final_year=final_year,
        placed=by_kind.get("placed_campus", 0) + by_kind.get("placed_offcampus", 0),
        higher_studies=by_kind.get("higher_studies", 0),
        entrepreneurship=by_kind.get("entrepreneurship", 0),
        exam_qualified=exam,
        not_placed=by_kind.get("not_placed", 0),
        unavailable=by_kind.get("unavailable", 0),
        unrecorded=max(final_year - with_outcome, 0),
        salaries=salaries,
    )


def recent_batches(conn, n: int, branch_id: int | None = None) -> list[int]:
    """The n most recent batch years that actually have students."""
    bf = "AND branch_id = :br" if branch_id else ""
    return [r[0] for r in conn.execute(text(f"""
        SELECT DISTINCT batch_year FROM students
         WHERE batch_year IS NOT NULL {bf}
         ORDER BY batch_year DESC LIMIT :n
    """), {"n": n, "br": branch_id}).all()]
