"""Student-facing endpoints beyond the shared dashboard/companies."""
from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile
from sqlalchemy import text

from ..attachments import safe_filename
from ..auth import Claims, get_claims
from ..db import tenant_connection

router = APIRouter(prefix="/api/me", tags=["portal"])


def _me(conn, claims: Claims) -> int:
    """This caller's students.id, or 404.

    Every student-owned query goes through this and filters on the result.
    Several endpoints used to carry no WHERE clause at all and a comment saying
    RLS would scope them to the caller — but the policies on questions,
    edit_requests and applications are college-scoped, not user-scoped, so
    "my questions" returned the whole college's. A comment is not a filter.
    """
    sid = conn.execute(text("SELECT id FROM students WHERE user_id = :u"),
                       {"u": claims.user_id}).scalar()
    if not sid:
        raise HTTPException(404, "No roster record linked to this account")
    return sid


def _student_only(claims: Claims) -> None:
    if claims.role != "student":
        raise HTTPException(403, "Student account required")


# =========================== drive attachments =============================
# RLS lets a student read any drive_attachments row in their college, because
# the row carries no secret. What decides whether they may see THIS one is
# whether the drive is published — status = 1 — which is the same filter
# my_drives applies. It is repeated explicitly in both queries below rather
# than assumed, because that check being missing from one query is exactly
# how the draft-drive leak happened.

@router.get("/drives/{company_id}/attachments")
def drive_attachments(company_id: int, claims: Claims = Depends(get_claims)):
    """JD and related files for a published drive. Metadata only."""
    if claims.role != "student":
        raise HTTPException(403, "Student account required")
    with tenant_connection(claims) as conn:
        published = conn.execute(text(
            "SELECT 1 FROM companies WHERE id = :c AND status = 1"),
            {"c": company_id}).scalar()
        if not published:
            raise HTTPException(404, "Drive not found")
        rows = conn.execute(text("""
            SELECT id, kind, filename, mime, byte_size, created_at
              FROM drive_attachments
             WHERE company_id = :c
             ORDER BY created_at
        """), {"c": company_id}).mappings().all()
    return [dict(r) for r in rows]


@router.get("/drives/{company_id}/attachments/{attachment_id}/download")
def download_drive_attachment(company_id: int, attachment_id: int,
                              claims: Claims = Depends(get_claims)):
    if claims.role != "student":
        raise HTTPException(403, "Student account required")
    with tenant_connection(claims) as conn:
        row = conn.execute(text("""
            SELECT a.filename, a.mime, a.data
              FROM drive_attachments a
              JOIN companies c ON c.id = a.company_id
             WHERE a.id = :a AND a.company_id = :c AND c.status = 1
        """), {"a": attachment_id, "c": company_id}).mappings().first()
    if not row:
        raise HTTPException(404, "Attachment not found")
    # Same helper the officer's download uses, so one file has one name.
    return Response(content=row["data"], media_type=row["mime"],
                    headers={"Content-Disposition":
                             f'attachment; filename="{safe_filename(row["filename"], row["mime"])}"'})


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

        sid = _me(conn, claims)
        # status = 1 keeps drafts hidden. The deadline check is new: an expired
        # drive was still listed with a working-looking Apply button, and
        # POST /register would then refuse it. A button that cannot succeed
        # should not be offered.
        drives = conn.execute(text("""
            SELECT c.id, c.name, c.category, c.package, c.deadline, c.status,
                   c.role_title, c.venue, c.test_date, c.restriction_note,
                   c.min_cgpa, c.max_backlogs, c.eligible_branches, c.eligibility_rules,
                   EXISTS (SELECT 1 FROM applications a
                            WHERE a.company_id = c.id AND a.student_id = :sid) AS applied,
                   EXISTS (SELECT 1 FROM drive_attachments da
                            WHERE da.company_id = c.id) AS has_files
            FROM companies c
            WHERE c.status = 1
              AND (c.deadline IS NULL OR c.deadline > now())
            ORDER BY c.package DESC NULLS LAST
        """), {"sid": sid}).mappings().all()

    out = []
    for d in drives:
        applied = bool(d["applied"])
        pol_ok, pol_reason = check_policy(policy, offers,
                                          float(d["package"]) if d["package"] else None)
        rules = d["eligibility_rules"] or legacy_rules_from_columns(dict(d))
        rule_ok, rule_reasons = evaluate_rules(rules, student)
        # An applied-for drive is not "ineligible" — the student already got in.
        # Reporting it as ineligible would show them a "why not" list for
        # something they have already done.
        eligible = (pol_ok and rule_ok) and not applied
        reasons = ([] if (pol_ok and rule_ok) else
                   ([pol_reason] if not pol_ok else []) + rule_reasons)
        out.append({"id": d["id"], "name": d["name"], "category": d["category"],
                    "package": float(d["package"]) if d["package"] else None,
                    "status": d["status"], "deadline": d["deadline"],
                    "role_title": d["role_title"], "venue": d["venue"],
                    "test_date": d["test_date"],
                    "restriction_note": d["restriction_note"],
                    "has_files": bool(d["has_files"]),
                    "applied": applied,
                    "eligible": eligible, "reasons": reasons})
    return out


@router.get("/applications")
def my_applications(claims: Claims = Depends(get_claims)):
    """The caller's own applications. Filtered here, not left to RLS."""
    _student_only(claims)
    with tenant_connection(claims) as conn:
        sid = _me(conn, claims)
        rows = conn.execute(text("""
            SELECT a.id, a.company_id, c.name AS company, c.category, c.package,
                   a.current_round, a.status, a.created_at
            FROM applications a JOIN companies c ON c.id = a.company_id
            WHERE a.student_id = :sid
            ORDER BY a.created_at DESC
        """), {"sid": sid}).mappings().all()
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
    _student_only(claims)          # was missing; every other student route has it
    with tenant_connection(claims) as conn:
        r = conn.execute(text("""
            SELECT r.filename, r.updated_at, octet_length(r.data)/1024 AS size_kb
            FROM resumes r JOIN students s ON s.id=r.student_id
            WHERE s.user_id=:u"""), {"u": claims.user_id}).mappings().first()
    return dict(r) if r else None


@router.get("/resume/download")
def download_my_resume(claims: Claims = Depends(get_claims)):
    """The student's own resume back.

    There was no way to read it: a student could upload, but never confirm
    what was actually stored. Since this file is what goes to companies,
    "I think I uploaded the right one" is not good enough — they need to open
    it. Scoped by user_id, so it can only ever return the caller's own.
    """
    _student_only(claims)
    with tenant_connection(claims) as conn:
        r = conn.execute(text("""
            SELECT r.filename, r.mime, r.data
            FROM resumes r JOIN students s ON s.id = r.student_id
            WHERE s.user_id = :u"""), {"u": claims.user_id}).mappings().first()
    if not r:
        raise HTTPException(404, "You haven't uploaded a resume yet")
    return Response(
        content=r["data"], media_type=r["mime"] or "application/pdf",
        headers={"Content-Disposition":
                 f'inline; filename="{safe_filename(r["filename"], r["mime"], "resume")}"'})


# =============================== profile ===================================
@router.get("/profile")
def my_profile(claims: Claims = Depends(get_claims)):
    _student_only(claims)
    with tenant_connection(claims) as conn:
        p = conn.execute(text("""
            SELECT s.id, s.roll_no, s.full_name, s.email, s.cgpa, s.backlogs,
                   b.code AS branch, s.verified, s.attributes,
                   (SELECT count(*) FROM applications a WHERE a.student_id=s.id) AS applications,
                   (SELECT count(*) FROM offers o WHERE o.student_id=s.id) AS offers,
                   -- The app reads has_resume in three places (the to-do list,
                   -- the profile card, the Apply gate) and it was never sent,
                   -- so it was always undefined: the card said "Not uploaded"
                   -- immediately after a successful upload.
                   EXISTS (SELECT 1 FROM resumes r WHERE r.student_id=s.id) AS has_resume,
                   (SELECT r.filename   FROM resumes r WHERE r.student_id=s.id) AS resume_filename,
                   (SELECT r.updated_at FROM resumes r WHERE r.student_id=s.id) AS resume_updated_at,
                   -- Feedback only opens once placed. The rule is enforced in
                   -- POST /feedback; this is so the app can say so up front
                   -- instead of letting a student write one and then 403.
                   EXISTS (SELECT 1 FROM offers o WHERE o.student_id=s.id) AS placed
            FROM students s JOIN branches b ON b.id=s.branch_id
            WHERE s.user_id=:u"""), {"u": claims.user_id}).mappings().first()
        if not p:
            raise HTTPException(404, "No roster record linked")
        # Was unfiltered: every student saw the whole college's correction
        # requests, which carry names, marks and email addresses.
        reqs = conn.execute(text("""
            SELECT id, field, requested_value, status, created_at FROM edit_requests
            WHERE student_id = :sid
            ORDER BY created_at DESC LIMIT 10"""), {"sid": p["id"]}).mappings().all()
    profile = dict(p)
    profile.pop("id", None)          # internal key, nothing client-side needs it
    return {"profile": profile, "edit_requests": [dict(r) for r in reqs]}


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
    """Only the caller's own questions.

    This previously had no WHERE clause and a comment claiming RLS showed
    "own questions + all answered ones (college-wide learning)". The policy is
    college-scoped, so what it actually showed was every student's questions to
    every student — including things like "my cgpa is 8.7, why am I not
    eligible", which is one student's marks on another student's screen.

    Answered questions are not shared learning. A question is written by
    someone describing their own situation, and they did not agree to publish
    it. If a shared FAQ is wanted later, it should be written by the placement
    cell, not harvested from student questions.
    """
    _student_only(claims)
    with tenant_connection(claims) as conn:
        sid = _me(conn, claims)
        rows = conn.execute(text("""
            SELECT id, title, body, status, answer, created_at
            FROM questions
            WHERE student_id = :sid
            ORDER BY created_at DESC LIMIT 200"""), {"sid": sid}).mappings().all()
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
    """The interview-experience library. Readable college-wide BY DESIGN —
    this is the 'junior login' of the old portal: juniors are roster students,
    so they read seniors' experiences right here.

    Deliberately unscoped, unlike /questions. The difference is consent: a
    student writes an experience in order to publish it to their juniors,
    having chosen what to put in it. A question is someone describing their own
    problem to the placement cell. Note that no student identity is selected
    here — company, role, CTC and advice only.
    """
    if claims.role not in ("student", "admin", "sub_admin", "owner"):
        raise HTTPException(403, "Not available for this account")
    with tenant_connection(claims) as conn:
        rows = conn.execute(text("""
            SELECT f.id, c.name AS company, f.role, f.ctc, f.rounds,
                   f.difficulty, f.topics, f.tips, f.created_at
            FROM feedback f JOIN companies c ON c.id=f.company_id
            ORDER BY f.created_at DESC LIMIT 200""")).mappings().all()
    return [dict(r) for r in rows]

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

