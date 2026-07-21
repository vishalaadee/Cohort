"""Cohort Score v0 — an explainable talent signal from data the platform
already collects, plus publicly-queryable coding profiles.

Design principles:
  * Student-visible: they see every component and how to improve.
  * Explainable: no black-box ML — weighted formula with named inputs.
  * Opt-in for sharing: the score is always computed (the student sees it),
    but recruiters only see it if the student flips consent_recruiter_share.
  * No partnerships needed: coding data comes from public APIs (Codeforces,
    CodeChef, LeetCode, GitHub) that students link voluntarily.

Components (v0 weights — tune with data after season 1):
  academics   (30%)  CGPA normalized to 0-100 (assuming 10-point scale)
  coding      (30%)  best normalized signal from linked profiles
  resume      (15%)  has resume + resume freshness
  engagement  (15%)  applications submitted, feedback written, Q&A activity
  extras      (10%)  extra attributes: no backlogs bonus, 10th/12th if available

Returns {"total": 0-100, "components": {...}, "tips": [...], "version": "v0"}
"""

from datetime import datetime, timezone

VERSION = "v0"
WEIGHTS = {"academics": 0.30, "coding": 0.30, "resume": 0.15,
           "engagement": 0.15, "extras": 0.10}


def compute_score(student: dict) -> dict:
    """student = flat dict with cgpa, backlogs, coding_profiles (json),
    attributes, has_resume, resume_age_days, applications_count,
    feedback_count, questions_count."""
    components = {}
    tips = []

    # ---- academics ----
    cgpa = float(student.get("cgpa") or 0)
    acad = min(100, cgpa * 10)  # 10-point scale → 0-100
    components["academics"] = round(acad)
    if cgpa < 7:
        tips.append("A CGPA above 7.0 opens most eligibility gates — semester improvement directly raises your score.")

    # ---- coding ----
    profiles = student.get("coding_profiles") or {}
    coding_signals = []
    if profiles.get("codeforces", {}).get("rating"):
        r = profiles["codeforces"]["rating"]
        coding_signals.append(min(100, max(0, (r - 800) / 12)))  # 800=0, 2000=100
    if profiles.get("codechef", {}).get("rating"):
        r = profiles["codechef"]["rating"]
        coding_signals.append(min(100, max(0, (r - 1000) / 10)))  # 1000=0, 2000=100
    if profiles.get("leetcode", {}).get("solved"):
        n = profiles["leetcode"]["solved"]
        coding_signals.append(min(100, n / 3))  # 300 solved = 100
    if profiles.get("github", {}).get("public_repos"):
        n = profiles["github"]["public_repos"]
        coding_signals.append(min(100, n * 5))  # 20 repos = 100
    coding = max(coding_signals) if coding_signals else 0
    components["coding"] = round(coding)
    if not coding_signals:
        tips.append("Link your CodeChef, Codeforces, LeetCode, or GitHub in Profile — verified coding activity is weighted 30%.")
    elif coding < 50:
        tips.append("Your coding score is below 50 — solving more problems or pushing projects to GitHub will raise it.")

    # ---- resume ----
    has_resume = bool(student.get("has_resume"))
    age = student.get("resume_age_days") or 999
    resume = 70 if has_resume else 0
    if has_resume and age < 30:
        resume = 100
    elif has_resume and age < 90:
        resume = 85
    components["resume"] = round(resume)
    if not has_resume:
        tips.append("Upload your resume — you can't register for drives without one, and it's 15% of your score.")
    elif age > 90:
        tips.append("Your resume is over 3 months old — updating it with recent projects boosts this component.")

    # ---- engagement ----
    apps = student.get("applications_count") or 0
    fb = student.get("feedback_count") or 0
    qs = student.get("questions_count") or 0
    eng = min(100, apps * 15 + fb * 25 + qs * 10)
    components["engagement"] = round(eng)
    if apps == 0:
        tips.append("Apply for at least one drive — engagement shows initiative to recruiters.")

    # ---- extras ----
    attrs = student.get("attributes") or {}
    backlogs = student.get("backlogs") or 0
    ext = 50  # baseline
    if backlogs == 0:
        ext += 30
    tenth = attrs.get("tenth_pct")
    twelfth = attrs.get("twelfth_pct")
    if tenth and float(tenth) >= 85:
        ext += 10
    if twelfth and float(twelfth) >= 85:
        ext += 10
    components["extras"] = round(min(100, ext))

    # ---- weighted total ----
    total = sum(components[k] * WEIGHTS[k] for k in WEIGHTS)
    return {
        "total": round(total),
        "components": components,
        "tips": tips[:4],  # max 4 actionable tips
        "version": VERSION,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }
