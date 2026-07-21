"""Student-facing endpoints beyond the shared dashboard/companies."""
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import text

from ..auth import Claims, get_claims
from ..db import tenant_connection

router = APIRouter(prefix="/api/me", tags=["portal"])


@router.get("/drives")
def my_drives(claims: Claims = Depends(get_claims)):
    """Every open drive with a per-student eligibility verdict and, when not
    eligible, the exact human-readable reasons. Runs the full pipeline:
    college placement policy first, then the drive's rule tree (or the legacy
    three-column fallback for drives created before configurable rules)."""
    if claims.role != "student":
        raise HTTPException(403, "Student account required")
    from ..eligibility import check_policy, evaluate_rules, legacy_rules_from_columns

    with tenant_connection(claims) as conn:
        me = conn.execute(text("""
            SELECT s.cgpa, s.backlogs, b.code AS branch, s.attributes
            FROM students s JOIN branches b ON b.id = s.branch_id
            WHERE s.user_id = :uid
        """), {"uid": claims.user_id}).mappings().first()
        if not me:
            raise HTTPException(404, "No roster record linked to this account")
        student = {"cgpa": float(me["cgpa"]) if me["cgpa"] is not None else None,
                   "backlogs": me["backlogs"], "branch": me["branch"],
                   **(me["attributes"] or {})}

        offers = [dict(r) for r in conn.execute(text("""
            SELECT c.package::float AS package
            FROM offers o
            JOIN students s  ON s.id = o.student_id
            JOIN companies c ON c.id = o.company_id
            WHERE s.user_id = :uid
        """), {"uid": claims.user_id}).mappings().all()]
        policy = conn.execute(text(
            "SELECT placement_policy FROM colleges WHERE id = :cid"
        ), {"cid": claims.college_id}).scalar() or {}

        drives = conn.execute(text("""
            SELECT id, name, category, package, deadline, status,
                   min_cgpa, max_backlogs, eligible_branches, eligibility_rules
            FROM companies ORDER BY package DESC NULLS LAST
        """)).mappings().all()

    out = []
    for d in drives:
        pol_ok, pol_reason = check_policy(policy, offers,
                                          float(d["package"]) if d["package"] else None)
        rules = d["eligibility_rules"] or legacy_rules_from_columns(dict(d))
        rule_ok, rule_reasons = evaluate_rules(rules, student)
        eligible = pol_ok and rule_ok
        reasons = ([] if eligible else
                   ([pol_reason] if not pol_ok else []) + rule_reasons)
        out.append({"id": d["id"], "name": d["name"], "category": d["category"],
                    "package": float(d["package"]) if d["package"] else None,
                    "status": d["status"], "eligible": eligible, "reasons": reasons})
    return out


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


# ============================ registration =================================
@router.post("/register/{company_id}")
def register_for_drive(company_id: int, claims: Claims = Depends(get_claims)):
    """Register for a drive. Gates, in order: drive open + deadline, resume on
    file (old-portal rule kept), full eligibility pipeline, no duplicate."""
    if claims.role != "student":
        raise HTTPException(403, "Student account required")
    from ..eligibility import check_policy, evaluate_rules, legacy_rules_from_columns
    with tenant_connection(claims) as conn:
        d = conn.execute(text("""
            SELECT id, name, package, status, deadline, min_cgpa, max_backlogs,
                   eligible_branches, eligibility_rules
            FROM companies WHERE id = :cid"""), {"cid": company_id}).mappings().first()
        if not d: raise HTTPException(404, "Drive not found")
        if d["status"] != 1: raise HTTPException(400, "Registrations are not open for this drive")
        if d["deadline"] is not None:
            past = conn.execute(text("SELECT :dl < now()"), {"dl": d["deadline"]}).scalar()
            if past: raise HTTPException(400, "The registration deadline has passed")

        me = conn.execute(text("""
            SELECT s.id, s.branch_id, s.cgpa, s.backlogs, b.code AS branch, s.attributes
            FROM students s JOIN branches b ON b.id = s.branch_id
            WHERE s.user_id = :uid"""), {"uid": claims.user_id}).mappings().first()
        if not me: raise HTTPException(404, "No roster record linked")

        has_resume = conn.execute(text(
            "SELECT 1 FROM resumes WHERE student_id = :sid"), {"sid": me["id"]}).scalar()
        if not has_resume:
            raise HTTPException(400, "Upload your resume before registering — companies receive it with your application")

        student = {"cgpa": float(me["cgpa"]) if me["cgpa"] is not None else None,
                   "backlogs": me["backlogs"], "branch": me["branch"], **(me["attributes"] or {})}
        offers = [dict(r) for r in conn.execute(text("""
            SELECT c.package::float AS package FROM offers o
            JOIN companies c ON c.id = o.company_id WHERE o.student_id = :sid
        """), {"sid": me["id"]}).mappings().all()]
        policy = conn.execute(text("SELECT placement_policy FROM colleges WHERE id=:c"),
                              {"c": claims.college_id}).scalar() or {}
        ok_p, why_p = check_policy(policy, offers, float(d["package"]) if d["package"] else None)
        rules = d["eligibility_rules"] or legacy_rules_from_columns(dict(d))
        ok_r, reasons = evaluate_rules(rules, student)
        if not (ok_p and ok_r):
            raise HTTPException(403, "Not eligible: " + "; ".join(([why_p] if not ok_p else []) + reasons))

        dup = conn.execute(text(
            "SELECT 1 FROM applications WHERE company_id=:c AND student_id=:s"),
            {"c": company_id, "s": me["id"]}).scalar()
        if dup: raise HTTPException(409, "You are already registered for this drive")

        conn.execute(text("""
            INSERT INTO applications (college_id, branch_id, company_id, student_id)
            VALUES (:col, :b, :c, :s)"""),
            {"col": claims.college_id, "b": me["branch_id"], "c": company_id, "s": me["id"]})
    return {"registered": True, "drive": d["name"]}


# =============================== resume ====================================
@router.post("/resume")
async def upload_resume(file: UploadFile, claims: Claims = Depends(get_claims)):
    if claims.role != "student": raise HTTPException(403, "Student account required")
    if file.content_type != "application/pdf":
        raise HTTPException(400, "Resume must be a PDF")
    data = await file.read()
    if len(data) > 2 * 1024 * 1024:
        raise HTTPException(400, "Resume must be under 2 MB")
    with tenant_connection(claims) as conn:
        sid = conn.execute(text("SELECT id FROM students WHERE user_id=:u"),
                           {"u": claims.user_id}).scalar()
        if not sid: raise HTTPException(404, "No roster record linked")
        conn.execute(text("""
            INSERT INTO resumes (college_id, student_id, filename, mime, data)
            VALUES (:c, :s, :f, :m, :d)
            ON CONFLICT (student_id) DO UPDATE
              SET filename=:f, mime=:m, data=:d, updated_at=now()"""),
            {"c": claims.college_id, "s": sid, "f": file.filename or "resume.pdf",
             "m": file.content_type, "d": data})
    return {"uploaded": True, "filename": file.filename, "size_kb": len(data)//1024}


@router.get("/resume")
def my_resume_meta(claims: Claims = Depends(get_claims)):
    with tenant_connection(claims) as conn:
        r = conn.execute(text("""
            SELECT r.filename, r.updated_at, octet_length(r.data)/1024 AS size_kb
            FROM resumes r JOIN students s ON s.id=r.student_id
            WHERE s.user_id=:u"""), {"u": claims.user_id}).mappings().first()
    return dict(r) if r else None


# =============================== profile ===================================
@router.get("/profile")
def my_profile(claims: Claims = Depends(get_claims)):
    if claims.role != "student": raise HTTPException(403, "Student account required")
    with tenant_connection(claims) as conn:
        p = conn.execute(text("""
            SELECT s.roll_no, s.full_name, s.email, s.cgpa, s.backlogs,
                   b.code AS branch, s.verified, s.attributes,
                   (SELECT count(*) FROM applications a WHERE a.student_id=s.id) AS applications,
                   (SELECT count(*) FROM offers o WHERE o.student_id=s.id) AS offers
            FROM students s JOIN branches b ON b.id=s.branch_id
            WHERE s.user_id=:u"""), {"u": claims.user_id}).mappings().first()
        reqs = conn.execute(text("""
            SELECT id, field, requested_value, status, created_at FROM edit_requests
            ORDER BY created_at DESC LIMIT 10""")).mappings().all()
    if not p: raise HTTPException(404, "No roster record linked")
    return {"profile": dict(p), "edit_requests": [dict(r) for r in reqs]}


@router.post("/edit-request")
def request_edit(payload: dict, claims: Claims = Depends(get_claims)):
    if claims.role != "student": raise HTTPException(403, "Student account required")
    field = (payload.get("field") or "").strip()
    value = (str(payload.get("requested_value") or "")).strip()
    ALLOWED = {"cgpa", "backlogs", "full_name", "email"}
    if not (field in ALLOWED or field.startswith("attr:")):
        raise HTTPException(400, "That field can't be changed via request")
    if not value: raise HTTPException(400, "Provide the corrected value")
    with tenant_connection(claims) as conn:
        s = conn.execute(text("SELECT id, cgpa, backlogs, full_name, email FROM students WHERE user_id=:u"),
                         {"u": claims.user_id}).mappings().first()
        if not s: raise HTTPException(404, "No roster record linked")
        current = str(s.get(field)) if field in s else ""
        conn.execute(text("""
            INSERT INTO edit_requests (college_id, student_id, field, current_value, requested_value, note)
            VALUES (:c, :s, :f, :cur, :val, :n)"""),
            {"c": claims.college_id, "s": s["id"], "f": field, "cur": current,
             "val": value, "n": (payload.get("note") or "")[:500]})
    return {"submitted": True}


# ================================= Q&A =====================================
@router.post("/questions")
def post_question(payload: dict, claims: Claims = Depends(get_claims)):
    if claims.role != "student": raise HTTPException(403, "Student account required")
    title = (payload.get("title") or "").strip()
    if not title: raise HTTPException(400, "Question title is required")
    with tenant_connection(claims) as conn:
        s = conn.execute(text("SELECT id, branch_id FROM students WHERE user_id=:u"),
                         {"u": claims.user_id}).mappings().first()
        conn.execute(text("""
            INSERT INTO questions (college_id, branch_id, student_id, title, body)
            VALUES (:c, :b, :s, :t, :bd)"""),
            {"c": claims.college_id, "b": s["branch_id"], "s": s["id"],
             "t": title[:300], "bd": (payload.get("body") or "")[:2000]})
    return {"posted": True}


@router.get("/questions")
def my_questions(claims: Claims = Depends(get_claims)):
    # RLS shows: own questions + all answered ones (college-wide learning)
    with tenant_connection(claims) as conn:
        rows = conn.execute(text("""
            SELECT id, title, body, status, answer, created_at
            FROM questions ORDER BY created_at DESC LIMIT 200""")).mappings().all()
    return [dict(r) for r in rows]


# ============================== feedback ===================================
@router.post("/feedback")
def submit_feedback(payload: dict, claims: Claims = Depends(get_claims)):
    """Opens only after placement — the old portal's rule, kept."""
    if claims.role != "student": raise HTTPException(403, "Student account required")
    with tenant_connection(claims) as conn:
        s = conn.execute(text("SELECT id FROM students WHERE user_id=:u"),
                         {"u": claims.user_id}).scalar()
        offer = conn.execute(text("""
            SELECT o.company_id FROM offers o WHERE o.student_id=:s
            ORDER BY o.created_at DESC LIMIT 1"""), {"s": s}).scalar()
        if not offer:
            raise HTTPException(403, "Feedback opens after you are placed — all the best!")
        diff = payload.get("difficulty")
        conn.execute(text("""
            INSERT INTO feedback (college_id, student_id, company_id, role, ctc,
                                  rounds, difficulty, topics, tips)
            VALUES (:col, :s, :co, :r, :ctc, :rd, :d, :tp, :ti)"""),
            {"col": claims.college_id, "s": s, "co": payload.get("company_id") or offer,
             "r": (payload.get("role") or "")[:120], "ctc": payload.get("ctc"),
             "rd": (payload.get("rounds") or "")[:300],
             "d": int(diff) if diff else None,
             "tp": (payload.get("topics") or "")[:500],
             "ti": (payload.get("tips") or "")[:2000]})
    return {"submitted": True}


@router.get("/feedback")
def browse_feedback(claims: Claims = Depends(get_claims)):
    """The interview-experience library. Readable by every student in the
    college — this IS the 'junior login' of the old portal: juniors are
    roster students, so they read seniors' experiences right here."""
    with tenant_connection(claims) as conn:
        rows = conn.execute(text("""
            SELECT f.id, c.name AS company, f.role, f.ctc, f.rounds,
                   f.difficulty, f.topics, f.tips, f.created_at
            FROM feedback f JOIN companies c ON c.id=f.company_id
            ORDER BY f.created_at DESC LIMIT 200""")).mappings().all()
    return [dict(r) for r in rows]
<<<<<<< Updated upstream
=======


# ============================ consent ======================================
@router.post("/consent")
def update_consent(payload: dict, claims: Claims = Depends(get_claims)):
    """Opt in/out of recruiter profile sharing. Revocable anytime."""
    if claims.role != "student": raise HTTPException(403, "Student account required")
    share = bool(payload.get("share"))
    with tenant_connection(claims) as conn:
        conn.execute(text("""
            UPDATE students SET consent_recruiter_share = :s, consent_updated_at = now()
            WHERE user_id = :u"""), {"s": share, "u": claims.user_id})
    return {"consent_recruiter_share": share}


@router.get("/consent")
def get_consent(claims: Claims = Depends(get_claims)):
    if claims.role != "student": raise HTTPException(403, "Student account required")
    with tenant_connection(claims) as conn:
        r = conn.execute(text("""
            SELECT consent_recruiter_share, consent_updated_at
            FROM students WHERE user_id = :u"""), {"u": claims.user_id}).mappings().first()
    return dict(r) if r else {"consent_recruiter_share": False}


# ======================== coding profiles ==================================
@router.put("/coding-profiles")
def save_coding_profiles(payload: dict, claims: Claims = Depends(get_claims)):
    """Save coding profile handles. Verification happens async (or on-demand)."""
    if claims.role != "student": raise HTTPException(403, "Student account required")
    import json
    allowed_keys = {"codeforces", "codechef", "leetcode", "github"}
    clean = {}
    for k in allowed_keys:
        if k in payload and payload[k]:
            handle = str(payload[k].get("handle", "")).strip()
            if handle:
                clean[k] = {"handle": handle, "verified": False}
    with tenant_connection(claims) as conn:
        conn.execute(text("""
            UPDATE students SET coding_profiles = CAST(:p AS jsonb)
            WHERE user_id = :u"""), {"p": json.dumps(clean), "u": claims.user_id})
    return {"saved": True, "profiles": clean}


# ============================ score ========================================
@router.get("/score")
def my_score(claims: Claims = Depends(get_claims)):
    """Compute and return the Cohort Score. Always visible to the student."""
    if claims.role != "student": raise HTTPException(403, "Student account required")
    from ..scoring import compute_score
    with tenant_connection(claims) as conn:
        row = conn.execute(text("""
            SELECT s.cgpa, s.backlogs, s.coding_profiles, s.attributes,
                   s.consent_recruiter_share,
                   (SELECT 1 FROM resumes r WHERE r.student_id=s.id) IS NOT NULL AS has_resume,
                   coalesce(extract(day FROM now() - (SELECT r.updated_at FROM resumes r WHERE r.student_id=s.id)), 999) AS resume_age_days,
                   (SELECT count(*) FROM applications a WHERE a.student_id=s.id) AS applications_count,
                   (SELECT count(*) FROM feedback f WHERE f.student_id=s.id) AS feedback_count,
                   (SELECT count(*) FROM questions q WHERE q.student_id=s.id) AS questions_count
            FROM students s WHERE s.user_id = :u
        """), {"u": claims.user_id}).mappings().first()
    if not row: raise HTTPException(404, "No roster record linked")
    score = compute_score(dict(row))
    # persist for the recruiter view
    import json
    with tenant_connection(claims) as conn:
        conn.execute(text("UPDATE students SET cohort_score = CAST(:s AS jsonb) WHERE user_id = :u"),
                     {"s": json.dumps(score), "u": claims.user_id})
    return {**score, "consent_recruiter_share": row["consent_recruiter_share"]}
>>>>>>> Stashed changes
