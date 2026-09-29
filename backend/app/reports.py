"""Accreditation arithmetic for NAAC, NBA and NIRF.

Pure functions over plain counts. No database, no SQLAlchemy, no FastAPI — so
every formula here is testable on its own, and the definitions live in exactly
one readable place rather than being buried in SQL.

THE WHOLE POINT OF THIS MODULE
------------------------------
The three bodies do not agree on what "placed" means, and a college filing all
three is doing the same count three different ways by hand:

    NAAC 5.2.1   placed / (final_year - higher_studies)
    NBA  4.6     (placed + higher_studies + entrepreneurship) / final_year
    NIRF GPH     placed / final_year  AND  higher_studies / final_year, reported
                 separately, averaged over three years, plus a median salary

On a batch of 100 final-year students with 50 placed, 12 in higher studies and
3 in entrepreneurship, those give 56.8%, 65.0% and 50.0%/12.0%. All three are
correct. None is interchangeable with another.

A SECOND, QUIETER PROBLEM
-------------------------
Most placement cells record employment and nothing else. All three frameworks
count higher studies, and two count entrepreneurship, so a college that tracks
only jobs under-reports itself. NIRF's own guidance gives the example of an
institution with 70% placement and 12% higher studies that reports 70% when its
GPH-eligible rate is 85%. That is a data-capture problem, not an effort problem,
and it is the reason `student_outcomes` exists.

WHAT IS DELIBERATELY NOT HERE
-----------------------------
Mark conversions I could not verify against a current official framework are
NOT invented. NAAC 5.2.1 and 5.2.2 publish explicit scoring bands and those are
implemented. NAAC 5.2.3's bands, and the NIRF GPH/GMS mark conversions, were not
obtainable, so those functions return the measured value and say plainly that
the band is unknown. A fabricated score that a college submits is worse than no
score at all.

Verify against the current manuals before a live submission:
  NAAC   the criterion-5 metrics of the manual in force (the framework was
         mid-reform toward binary/MBGL when this was written; status unconfirmed)
  NBA    SAR format, UG Engineering, criterion 4.6
  NIRF   the year's Engineering ranking framework, Graduation Outcomes
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median
from typing import Iterable, Sequence


def _pct(numerator: float, denominator: float) -> float:
    """Percentage, rounded to one decimal. Zero denominator yields 0.0 rather
    than an exception: an empty batch is a legitimate state (a college that has
    just onboarded), and a report that crashes on it is useless."""
    if not denominator:
        return 0.0
    return round((numerator / denominator) * 100, 1)


def _band(value: float, bands: Sequence[tuple[float, int]]) -> int:
    """Map a percentage onto a scoring band.

    `bands` is ordered high to low as (threshold, score), and the comparison is
    `value >= threshold`. So a published band of "60-70 => 3" is entered as
    (60, 3) and a value of exactly 70 scores 4, not 3 — upper bounds belong to
    the band above. That reading is the standard one, but it is the kind of
    boundary an assessor will query, so it is stated here rather than implied.
    """
    for threshold, score in bands:
        if value >= threshold:
            return score
    return 0


# --------------------------------------------------------------------------
# NAAC — Criterion 5, Student Support and Progression
# --------------------------------------------------------------------------

# 5.2.1 Placement of outgoing students (15 marks)
NAAC_521_BANDS = [(70, 4), (60, 3), (50, 2), (40, 1)]

# 5.2.2 Progression to higher education (15 marks)
NAAC_522_BANDS = [(40, 4), (30, 3), (20, 2), (5, 1)]


def naac_5_2_1(*, final_year: int, placed: int, higher_studies: int) -> dict:
    """Placement of outgoing students.

        placed / (final_year - higher_studies) * 100

    Note what the denominator does: students who progressed to higher education
    are REMOVED, not counted as unplaced. A college that cannot identify who
    went on to study is penalised twice — it loses 5.2.2 marks and inflates its
    own 5.2.1 denominator.
    """
    eligible = max(final_year - higher_studies, 0)
    pct = _pct(placed, eligible)
    return {
        "metric": "NAAC 5.2.1",
        "label": "Placement of outgoing students",
        "percentage": pct,
        "numerator": placed,
        "denominator": eligible,
        "denominator_note": "final-year students minus those in higher education",
        "score": _band(pct, NAAC_521_BANDS),
        "max_score": 4,
        "marks": 15,
    }


def naac_5_2_2(*, final_year: int, higher_studies: int) -> dict:
    """Progression to higher education.

    Requires, per student, the institution and programme joined plus a link to
    proof of continuation — which is why `student_outcomes` carries
    institution_name / program_name and `outcome_documents` exists.
    """
    pct = _pct(higher_studies, final_year)
    return {
        "metric": "NAAC 5.2.2",
        "label": "Progression to higher education",
        "percentage": pct,
        "numerator": higher_studies,
        "denominator": final_year,
        "score": _band(pct, NAAC_522_BANDS),
        "max_score": 4,
        "marks": 15,
        "evidence_required": "institution, programme and proof of continuation per student",
    }


def naac_5_2_3(*, final_year: int, exam_qualified: int) -> dict:
    """Students qualifying in state / national / international examinations
    (NET, SLET, GATE, UPSC and similar), with qualifying certificates.

    The scoring band for this metric could not be verified against a current
    NAAC manual, so no score is returned. The measured value is reported and
    the band is flagged as unknown rather than guessed.
    """
    pct = _pct(exam_qualified, final_year)
    return {
        "metric": "NAAC 5.2.3",
        "label": "Qualifying in competitive examinations",
        "percentage": pct,
        "numerator": exam_qualified,
        "denominator": final_year,
        "score": None,
        "max_score": 4,
        "marks": 15,
        "band_unverified": True,
        "note": ("Scoring band not verified against a current NAAC manual. "
                 "Confirm before submission."),
        "evidence_required": "exam name and qualifying certificate per student",
    }


# --------------------------------------------------------------------------
# NBA — UG Engineering, Criterion 4.6
# --------------------------------------------------------------------------

def nba_4_6_index(*, final_year: int, placed: int,
                  higher_studies: int, entrepreneurship: int) -> float:
    """The NBA Placement Index for a single batch.

        P = ((X + Y + Z) / FS) * 100

    X placed, Y higher studies, Z entrepreneurship, FS all final-year students.
    Unlike NAAC 5.2.1 the denominator is everyone — nobody is removed.
    """
    return _pct(placed + higher_studies + entrepreneurship, final_year)


def nba_4_6(batches: Sequence[dict]) -> dict:
    """NBA 4.6 over the three most recent batches (LYG, LYGm1, LYGm2).

        Points = 0.3 * (average Placement Index across the three batches)

    Assessed per PROGRAMME, so callers pass one branch's batches at a time. A
    college with eight NBA-seeking departments produces this eight times over.

    Each element of `batches` is {batch_year, final_year, placed,
    higher_studies, entrepreneurship}.
    """
    rows = []
    for b in batches:
        idx = nba_4_6_index(
            final_year=b.get("final_year", 0),
            placed=b.get("placed", 0),
            higher_studies=b.get("higher_studies", 0),
            entrepreneurship=b.get("entrepreneurship", 0),
        )
        rows.append({**b, "placement_index": idx})

    avg = round(sum(r["placement_index"] for r in rows) / len(rows), 2) if rows else 0.0
    return {
        "metric": "NBA 4.6",
        "label": "Placement, Higher Studies and Entrepreneurship",
        "batches": rows,
        "average_placement_index": avg,
        "points": round(0.3 * avg, 2),
        "max_points": 30,
        "batches_required": 3,
        "batches_supplied": len(rows),
        "complete": len(rows) >= 3,
        "scope": "per programme (branch), three batches",
    }


# --------------------------------------------------------------------------
# NIRF — Engineering, Graduation Outcomes
# --------------------------------------------------------------------------

def nirf_gph(batches: Sequence[dict]) -> dict:
    """Graduation Outcomes: Placement and Higher Studies (GPH, 40 marks).

    Percentage placed and percentage in higher studies, reported SEPARATELY and
    averaged over the previous three years. The mark conversion from those
    percentages was not obtainable, so it is not invented.
    """
    rows = []
    for b in batches:
        fy = b.get("final_year", 0)
        rows.append({
            "batch_year": b.get("batch_year"),
            "final_year": fy,
            "placed_pct": _pct(b.get("placed", 0), fy),
            "higher_studies_pct": _pct(b.get("higher_studies", 0), fy),
        })
    n = len(rows) or 1
    return {
        "metric": "NIRF GPH",
        "label": "Placement and Higher Studies",
        "years": rows,
        "avg_placed_pct": round(sum(r["placed_pct"] for r in rows) / n, 1),
        "avg_higher_studies_pct": round(sum(r["higher_studies_pct"] for r in rows) / n, 1),
        "marks": 40,
        "years_required": 3,
        "years_supplied": len(rows),
        "complete": len(rows) >= 3,
        "mark_conversion_unverified": True,
    }


def nirf_gms(salaries_by_year: dict[int, Iterable[float]]) -> dict:
    """Graduation Outcomes: Median Salary (GMS, 25 marks).

    Median — not mean. One student at a very high package must not move the
    figure, which is exactly why the framework asks for the median.

    Salaries come from `offers.annual_ctc` / `student_outcomes.annual_ctc`, the
    amount actually offered, not `companies.package`, which is what was
    advertised. Those differ, and only the former is defensible.
    """
    per_year = []
    for year in sorted(salaries_by_year):
        vals = [float(v) for v in salaries_by_year[year] if v is not None]
        per_year.append({
            "batch_year": year,
            "n": len(vals),
            "median_salary": round(median(vals), 2) if vals else None,
        })
    medians = [r["median_salary"] for r in per_year if r["median_salary"] is not None]
    return {
        "metric": "NIRF GMS",
        "label": "Median Salary",
        "years": per_year,
        "three_year_median_of_medians": round(median(medians), 2) if medians else None,
        "marks": 25,
        "years_required": 3,
        "years_supplied": len(per_year),
        "complete": len(per_year) >= 3,
        "mark_conversion_unverified": True,
        "note": "Median of actual offered CTC, not the advertised package.",
    }


# --------------------------------------------------------------------------
# The reconciliation — this is the demo
# --------------------------------------------------------------------------

@dataclass
class BatchCounts:
    """One batch, counted once, as every metric below needs it."""
    batch_year: int | None = None
    final_year: int = 0
    placed: int = 0                 # campus + off-campus, DISTINCT STUDENTS
    higher_studies: int = 0
    entrepreneurship: int = 0
    exam_qualified: int = 0
    not_placed: int = 0
    unavailable: int = 0
    unrecorded: int = 0             # final-year students with no outcome at all
    salaries: list[float] = field(default_factory=list)


def reconcile(counts: BatchCounts) -> dict:
    """Every framework's answer for one batch, from one set of counts.

    This is the screen that sells the product. A placement officer who files
    NAAC, NBA and NIRF by hand has reconciled these three numbers with a
    calculator and never been sure they agree. Showing all three derived from
    the same row set, with the differing denominators made explicit, is the
    fifteen-second demonstration.
    """
    c = counts
    naac_1 = naac_5_2_1(final_year=c.final_year, placed=c.placed,
                        higher_studies=c.higher_studies)
    naac_2 = naac_5_2_2(final_year=c.final_year, higher_studies=c.higher_studies)
    naac_3 = naac_5_2_3(final_year=c.final_year, exam_qualified=c.exam_qualified)
    nba_index = nba_4_6_index(final_year=c.final_year, placed=c.placed,
                              higher_studies=c.higher_studies,
                              entrepreneurship=c.entrepreneurship)

    plain = _pct(c.placed, c.final_year)
    salaries = [float(s) for s in c.salaries if s is not None]

    # Data-completeness is reported as loudly as the numbers. A college whose
    # outcomes are 40% unrecorded is not looking at its placement rate; it is
    # looking at the fraction it happens to have written down, and every metric
    # below is understated by the remainder.
    accounted = (c.placed + c.higher_studies + c.entrepreneurship
                 + c.not_placed + c.unavailable)
    coverage = _pct(accounted, c.final_year)

    return {
        "batch_year": c.batch_year,
        "counts": {
            "final_year_students": c.final_year,
            "placed": c.placed,
            "higher_studies": c.higher_studies,
            "entrepreneurship": c.entrepreneurship,
            "exam_qualified": c.exam_qualified,
            "not_placed": c.not_placed,
            "unavailable": c.unavailable,
            "unrecorded": c.unrecorded,
        },
        "plain_placement_rate": plain,
        "plain_note": "placed students / final-year students — the number people say out loud",
        "naac": {"5.2.1": naac_1, "5.2.2": naac_2, "5.2.3": naac_3},
        "nba": {
            "metric": "NBA 4.6",
            "placement_index": nba_index,
            "formula": "(placed + higher studies + entrepreneurship) / final-year students",
            "note": "Points need three batches; see nba_4_6().",
        },
        "nirf": {
            "metric": "NIRF GPH / GMS",
            "placed_pct": plain,
            "higher_studies_pct": _pct(c.higher_studies, c.final_year),
            "median_salary": round(median(salaries), 2) if salaries else None,
            "salary_n": len(salaries),
            "note": "GPH is a three-year average; this is one year's input.",
        },
        "why_they_differ": [
            "NAAC 5.2.1 removes higher-studies students from the denominator.",
            "NBA 4.6 adds higher studies and entrepreneurship to the numerator "
            "and keeps every final-year student in the denominator.",
            "NIRF reports placement and higher studies as separate percentages "
            "and adds a median salary.",
        ],
        "data_quality": {
            "coverage_pct": coverage,
            "unrecorded": c.unrecorded,
            "complete": c.unrecorded == 0,
            "warning": (None if c.unrecorded == 0 else
                        f"{c.unrecorded} final-year student(s) have no recorded outcome. "
                        f"Every figure above understates the college until they do."),
        },
    }
