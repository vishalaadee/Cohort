"""Admin console endpoints beyond roster management."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from ..auth import Claims, get_claims
from ..db import tenant_connection
from ..eligibility import RuleError, check_policy, evaluate_rules, legacy_rules_from_columns

router = APIRouter(prefix="/api/admin", tags=["admin-extra"])

ROUNDS = ["resume_screening", "online_assessment", "technical_1", "technical_2",
          "technical_3", "managerial", "hr", "final_placement"]
BUILTIN_ATTRS = [
    {"key": "cgpa", "label": "CGPA", "data_type": "number"},
    {"key": "backlogs", "label": "Backlogs", "data_type": "number"},
    {"key": "branch", "label": "Branch", "data_type": "text"},
]


def _staff(claims: Claims, admin_only=False):
    allowed = ("owner", "admin") if admin_only else ("owner", "admin", "sub_admin")
    if claims.role not in allowed:
        raise HTTPException(403, "Placement-cell access required")


# ------------------------------ drives ------------------------------------
@router.post("/companies")
def create_drive(payload: dict, claims: Claims = Depends(get_claims)):
    _staff(claims, admin_only=True)
    name = (payload.get("name") or "").strip()
    if not name: raise HTTPException(400, "Company name is required")
    with tenant_connection(claims) as conn:
        cid = conn.execute(text("""
            INSERT INTO companies (college_id, name, category, package, min_cgpa,
                                   max_backlogs, eligible_branches, deadline, status)
            VALUES (:col, :n, :cat, :p, 0, 99, '{}', :dl, 0) RETURNING id"""),
            {"col": claims.college_id, "n": name[:200],
             "cat": payload.get("category"), "p": payload.get("package"),
             "dl": payload.get("deadline")}).scalar_one()
    return {"id": cid, "created": True}


@router.patch("/companies/{cid}")
def update_drive(cid: int, payload: dict, claims: Claims = Depends(get_claims)):
    _staff(claims, admin_only=True)
    sets, params = [], {"cid": cid}
    for f in ("name", "category", "package", "deadline", "status"):
        if f in payload:
            sets.append(f"{f} = :{f}"); params[f] = payload[f]
    if not sets: raise HTTPException(400, "Nothing to update")
    with tenant_connection(claims) as conn:
        n = conn.execute(text(f"UPDATE companies SET {', '.join(sets)} WHERE id=:cid"),
                         params).rowcount
    if not n: raise HTTPException(404, "Drive not found")
    return {"updated": True}


# ------------------------- rule builder + policy ---------------------------
@router.get("/attributes")
def list_attributes(claims: Claims = Depends(get_claims)):
    _staff(claims)
    with tenant_connection(claims) as conn:
        custom = conn.execute(text(
            "SELECT key, label, data_type FROM attribute_defs ORDER BY key"
        )).mappings().all()
    return BUILTIN_ATTRS + [dict(r) for r in custom]


@router.post("/attributes")
def add_attribute(payload: dict, claims: Claims = Depends(get_claims)):
    _staff(claims, admin_only=True)
    key = (payload.get("key") or "").strip().lower().replace(" ", "_")
    if not key or key in {a["key"] for a in BUILTIN_ATTRS}:
        raise HTTPException(400, "Invalid or reserved attribute key")
    if payload.get("data_type") not in ("number", "text", "boolean"):
        raise HTTPException(400, "data_type must be number, text or boolean")
    with tenant_connection(claims) as conn:
        conn.execute(text("""
            INSERT INTO attribute_defs (college_id, key, label, data_type)
            VALUES (:c, :k, :l, :t) ON CONFLICT (college_id, key) DO NOTHING"""),
            {"c": claims.college_id, "k": key,
             "l": (payload.get("label") or key)[:80], "t": payload["data_type"]})
    return {"added": True, "key": key}


def _validate_rules(rules):
    """Dry-run the tree so a broken rule can never be saved."""
    if rules in (None, {}, []): return None
    if not isinstance(rules, dict): raise HTTPException(400, "Rules must be an object")
    try:
        evaluate_rules(rules, {"cgpa": 8, "backlogs": 0, "branch": "CSE"})
    except RuleError as e:
        raise HTTPException(400, f"Invalid rule: {e}")
    return rules


@router.get("/companies/{cid}/rules")
def get_rules(cid: int, claims: Claims = Depends(get_claims)):
    _staff(claims)
    with tenant_connection(claims) as conn:
        row = conn.execute(text(
            "SELECT eligibility_rules FROM companies WHERE id=:cid"), {"cid": cid}).first()
    if not row: raise HTTPException(404, "Drive not found")
    return row[0] or {}


@router.put("/companies/{cid}/rules")
def save_rules(cid: int, payload: dict, claims: Claims = Depends(get_claims)):
    _staff(claims, admin_only=True)
    rules = _validate_rules(payload.get("rules"))
    with tenant_connection(claims) as conn:
        import json
        n = conn.execute(text(
            "UPDATE companies SET eligibility_rules = CAST(:r AS jsonb) WHERE id=:cid"),
            {"r": json.dumps(rules) if rules else None, "cid": cid}).rowcount
    if not n: raise HTTPException(404, "Drive not found")
    return {"saved": True}


@router.get("/companies/{cid}/eligibility-preview")
def eligibility_preview(cid: int, claims: Claims = Depends(get_claims)):
    """'142 of 480 students eligible' — before the drive even opens."""
    _staff(claims)
    with tenant_connection(claims) as conn:
        d = conn.execute(text("""
            SELECT package, min_cgpa, max_backlogs, eligible_branches, eligibility_rules
            FROM companies WHERE id=:cid"""), {"cid": cid}).mappings().first()
        if not d: raise HTTPException(404, "Drive not found")
        policy = conn.execute(text("SELECT placement_policy FROM colleges WHERE id=:c"),
                              {"c": claims.college_id}).scalar() or {}
        students = conn.execute(text("""
            SELECT s.id, s.cgpa, s.backlogs, b.code AS branch, s.attributes,
              (SELECT coalesce(max(c2.package)::float,0) FROM offers o
                JOIN companies c2 ON c2.id=o.company_id
                WHERE o.student_id=s.id) AS best_offer
            FROM students s JOIN branches b ON b.id=s.branch_id""")).mappings().all()
    rules = d["eligibility_rules"] or legacy_rules_from_columns(dict(d))
    pkg = float(d["package"]) if d["package"] else None
    eligible = 0
    for s in students:
        offers = [{"package": s["best_offer"]}] if s["best_offer"] else []
        ok_p, _ = check_policy(policy, offers, pkg)
        stu = {"cgpa": float(s["cgpa"]) if s["cgpa"] is not None else None,
               "backlogs": s["backlogs"], "branch": s["branch"], **(s["attributes"] or {})}
        ok_r, _ = evaluate_rules(rules, stu)
        eligible += 1 if (ok_p and ok_r) else 0
    return {"eligible": eligible, "total": len(students)}


@router.get("/policy")
def get_policy(claims: Claims = Depends(get_claims)):
    _staff(claims)
    with tenant_connection(claims) as conn:
        p = conn.execute(text("SELECT placement_policy FROM colleges WHERE id=:c"),
                         {"c": claims.college_id}).scalar()
    return p or {}


@router.put("/policy")
def save_policy(payload: dict, claims: Claims = Depends(get_claims)):
    _staff(claims, admin_only=True)
    import json
    allowed = {"one_offer", "max_offers", "slabs", "upgrade", "multiplier"}
    clean = {k: v for k, v in (payload or {}).items() if k in allowed}
    if clean.get("upgrade") not in (None, "none", "higher_slab", "multiplier", "both"):
        raise HTTPException(400, "upgrade must be none|higher_slab|multiplier|both")
    check_policy(clean, [{"package": 500000}], 900000)  # dry-run for shape errors
    with tenant_connection(claims) as conn:
        conn.execute(text("UPDATE colleges SET placement_policy = CAST(:p AS jsonb) WHERE id=:c"),
                     {"p": json.dumps(clean), "c": claims.college_id})
    return {"saved": True, "policy": clean}


# ------------------- registrants + pipeline write-side ---------------------
@router.get("/companies/{cid}/registrations")
def registrants(cid: int, claims: Claims = Depends(get_claims)):
    _staff(claims)
    with tenant_connection(claims) as conn:
        rows = conn.execute(text("""
            SELECT a.id, s.roll_no, s.full_name, b.code AS branch, s.cgpa,
                   a.current_round, a.status,
                   (SELECT 1 FROM resumes r WHERE r.student_id=s.id) IS NOT NULL AS has_resume
            FROM applications a
            JOIN students s ON s.id=a.student_id
            JOIN branches b ON b.id=a.branch_id
            WHERE a.company_id=:cid ORDER BY s.roll_no"""), {"cid": cid}).mappings().all()
    return [dict(r) for r in rows]


@router.patch("/applications/{aid}")
def advance_application(aid: int, payload: dict, claims: Claims = Depends(get_claims)):
    """Advance/reject/place. Placing also records the offer."""
    _staff(claims)
    rnd, status = payload.get("current_round"), payload.get("status")
    if rnd and rnd not in ROUNDS: raise HTTPException(400, "Unknown round")
    if status and status not in ("active", "placed", "rejected", "withdrawn"):
        raise HTTPException(400, "Unknown status")
    with tenant_connection(claims) as conn:
        app_row = conn.execute(text("""
            SELECT college_id, student_id, company_id FROM applications WHERE id=:a"""),
            {"a": aid}).mappings().first()
        if not app_row: raise HTTPException(404, "Application not found")
        sets, params = [], {"a": aid}
        if rnd: sets.append("current_round=:r"); params["r"] = rnd
        if status: sets.append("status=:s"); params["s"] = status
        if sets:
            conn.execute(text(f"UPDATE applications SET {', '.join(sets)} WHERE id=:a"), params)
        if status == "placed":
            conn.execute(text("""
                INSERT INTO offers (college_id, student_id, company_id, category)
                SELECT :col, :st, :co, c.category FROM companies c WHERE c.id=:co
                ON CONFLICT DO NOTHING"""),
                {"col": app_row["college_id"], "st": app_row["student_id"],
                 "co": app_row["company_id"]})
    return {"updated": True}


# --------------------------- notes + calendar ------------------------------
@router.get("/notes")
def list_notes(claims: Claims = Depends(get_claims)):
    _staff(claims)
    with tenant_connection(claims) as conn:
        rows = conn.execute(text("""
            SELECT n.id, n.note_date, n.kind, n.title, n.body, c.name AS company
            FROM company_notes n LEFT JOIN companies c ON c.id=n.company_id
            ORDER BY n.note_date, n.id""")).mappings().all()
    return [dict(r) for r in rows]


@router.post("/notes")
def add_note(payload: dict, claims: Claims = Depends(get_claims)):
    _staff(claims)
    if not payload.get("title") or not payload.get("note_date"):
        raise HTTPException(400, "title and note_date are required")
    if payload.get("kind", "note") not in ("visit", "test", "deadline", "note"):
        raise HTTPException(400, "kind must be visit|test|deadline|note")
    with tenant_connection(claims) as conn:
        conn.execute(text("""
            INSERT INTO company_notes (college_id, company_id, note_date, kind, title, body)
            VALUES (:c, :co, :d, :k, :t, :b)"""),
            {"c": claims.college_id, "co": payload.get("company_id"),
             "d": payload["note_date"], "k": payload.get("kind", "note"),
             "t": payload["title"][:200], "b": (payload.get("body") or "")[:2000]})
    return {"added": True}


@router.delete("/notes/{nid}")
def delete_note(nid: int, claims: Claims = Depends(get_claims)):
    _staff(claims)
    with tenant_connection(claims) as conn:
        n = conn.execute(text("DELETE FROM company_notes WHERE id=:n"), {"n": nid}).rowcount
    if not n: raise HTTPException(404, "Note not found")
    return {"deleted": True}


# ------------------------- Q&A moderation ---------------------------------
@router.get("/questions")
def all_questions(claims: Claims = Depends(get_claims)):
    _staff(claims)  # RLS: admin sees all; sub_admin sees own branch
    with tenant_connection(claims) as conn:
        rows = conn.execute(text("""
            SELECT q.id, q.title, q.body, q.status, q.answer, q.created_at,
                   b.code AS branch, s.roll_no
            FROM questions q
            LEFT JOIN branches b ON b.id=q.branch_id
            LEFT JOIN students s ON s.id=q.student_id
            ORDER BY q.created_at DESC LIMIT 300""")).mappings().all()
    return [dict(r) for r in rows]


@router.patch("/questions/{qid}")
def moderate_question(qid: int, payload: dict, claims: Claims = Depends(get_claims)):
    """CR escalates to the PO; PO answers (publishing it college-wide)."""
    _staff(claims)
    action = payload.get("action")
    with tenant_connection(claims) as conn:
        if action == "escalate":
            n = conn.execute(text(
                "UPDATE questions SET status='escalated' WHERE id=:q AND status='open'"),
                {"q": qid}).rowcount
        elif action == "answer":
            if claims.role not in ("owner", "admin"):
                raise HTTPException(403, "Only the placement officer can answer")
            ans = (payload.get("answer") or "").strip()
            if not ans: raise HTTPException(400, "Answer text required")
            n = conn.execute(text(
                "UPDATE questions SET status='answered', answer=:a WHERE id=:q"),
                {"a": ans[:2000], "q": qid}).rowcount
        else:
            raise HTTPException(400, "action must be escalate|answer")
    if not n: raise HTTPException(404, "Question not found (or already handled)")
    return {"ok": True}


# ---------------------- edit-request approvals -----------------------------
@router.get("/edit-requests")
def pending_edits(claims: Claims = Depends(get_claims)):
    _staff(claims)
    with tenant_connection(claims) as conn:
        rows = conn.execute(text("""
            SELECT e.id, s.roll_no, s.full_name, e.field, e.current_value,
                   e.requested_value, e.note, e.status, e.created_at
            FROM edit_requests e JOIN students s ON s.id=e.student_id
            ORDER BY (e.status='pending') DESC, e.created_at DESC LIMIT 200""")).mappings().all()
    return [dict(r) for r in rows]


@router.patch("/edit-requests/{rid}")
def decide_edit(rid: int, payload: dict, claims: Claims = Depends(get_claims)):
    _staff(claims, admin_only=True)
    decision = payload.get("decision")
    if decision not in ("approved", "rejected"):
        raise HTTPException(400, "decision must be approved|rejected")
    with tenant_connection(claims) as conn:
        req = conn.execute(text("""
            SELECT student_id, field, requested_value FROM edit_requests
            WHERE id=:r AND status='pending'"""), {"r": rid}).mappings().first()
        if not req: raise HTTPException(404, "Pending request not found")
        if decision == "approved":
            f, v = req["field"], req["requested_value"]
            if f == "cgpa":
                conn.execute(text("UPDATE students SET cgpa=:v WHERE id=:s"),
                             {"v": float(v), "s": req["student_id"]})
            elif f == "backlogs":
                conn.execute(text("UPDATE students SET backlogs=:v WHERE id=:s"),
                             {"v": int(v), "s": req["student_id"]})
            elif f in ("full_name", "email"):
                conn.execute(text(f"UPDATE students SET {f}=:v WHERE id=:s"),
                             {"v": v, "s": req["student_id"]})
            elif f.startswith("attr:"):
                import json
                conn.execute(text("""
                    UPDATE students SET attributes =
                      attributes || CAST(:j AS jsonb) WHERE id=:s"""),
                    {"j": json.dumps({f[5:]: _coerce(v)}), "s": req["student_id"]})
        conn.execute(text("UPDATE edit_requests SET status=:d WHERE id=:r"),
                     {"d": decision, "r": rid})
    return {"decision": decision}


def _coerce(v: str):
    try: return float(v) if "." in v else int(v)
    except ValueError:
        return {"true": True, "false": False}.get(v.lower(), v)


# --------------------------- analytics ------------------------------------
@router.get("/analytics")
def analytics(claims: Claims = Depends(get_claims)):
    """Placement-officer analytics: overview, branch performance, CTC
    distribution, drive-wise conversion, CGPA insight, offer timeline, and
    the actionable list of students who haven't applied anywhere."""
    _staff(claims)
    with tenant_connection(claims) as conn:
        overview = conn.execute(text("""
            SELECT
              (SELECT count(*) FROM students)                             AS students,
              (SELECT count(DISTINCT student_id) FROM offers)             AS placed,
              (SELECT count(*) FROM offers)                               AS offers,
              (SELECT count(*) FROM applications)                         AS applications,
              (SELECT count(*) FROM companies WHERE status=1)             AS open_drives
        """)).mappings().one()
        pkg = conn.execute(text("""
            SELECT coalesce(avg(c.package),0)::bigint AS avg,
                   coalesce(max(c.package),0)::bigint AS max,
                   coalesce(percentile_cont(0.5) WITHIN GROUP (ORDER BY c.package),0)::bigint AS median
            FROM offers o JOIN companies c ON c.id=o.company_id""")).mappings().one()
        branch = conn.execute(text("""
            SELECT b.code AS branch,
                   count(DISTINCT s.id) AS students,
                   count(DISTINCT o.student_id) AS placed,
                   coalesce(avg(c.package) FILTER (WHERE o.id IS NOT NULL),0)::bigint AS avg_package
            FROM branches b
            LEFT JOIN students s ON s.branch_id=b.id
            LEFT JOIN offers o ON o.student_id=s.id
            LEFT JOIN companies c ON c.id=o.company_id
            GROUP BY b.code ORDER BY b.code""")).mappings().all()
        ctc_dist = conn.execute(text("""
            SELECT width_bucket(c.package, ARRAY[500000,1000000,1500000]) AS bucket,
                   count(*) AS offers
            FROM offers o JOIN companies c ON c.id=o.company_id
            WHERE c.package IS NOT NULL GROUP BY 1 ORDER BY 1""")).mappings().all()
        drives = conn.execute(text("""
            SELECT c.name, c.category, c.package, c.status,
                   count(a.id) AS registered,
                   count(a.id) FILTER (WHERE a.status='active')   AS in_process,
                   count(a.id) FILTER (WHERE a.status='placed')   AS placed,
                   count(a.id) FILTER (WHERE a.status='rejected') AS rejected
            FROM companies c LEFT JOIN applications a ON a.company_id=c.id
            GROUP BY c.id ORDER BY c.package DESC NULLS LAST""")).mappings().all()
        rounds = conn.execute(text("""
            SELECT current_round AS round, count(*) AS count
            FROM applications WHERE status='active'
            GROUP BY 1""")).mappings().all()
        cgpa = conn.execute(text("""
            SELECT coalesce(avg(s.cgpa) FILTER (WHERE o.id IS NOT NULL),0)::numeric(4,2) AS placed_avg,
                   coalesce(avg(s.cgpa) FILTER (WHERE o.id IS NULL),0)::numeric(4,2)     AS unplaced_avg
            FROM students s LEFT JOIN offers o ON o.student_id=s.id""")).mappings().one()
        timeline = conn.execute(text("""
            SELECT to_char(date_trunc('month', o.created_at),'Mon YYYY') AS month,
                   date_trunc('month', o.created_at) AS m, count(*) AS offers
            FROM offers o GROUP BY 1,2 ORDER BY 2""")).mappings().all()
        never_applied = conn.execute(text("""
            SELECT count(*) FROM students s
            WHERE NOT EXISTS (SELECT 1 FROM applications a WHERE a.student_id=s.id)""")).scalar()
        no_resume = conn.execute(text("""
            SELECT count(*) FROM students s
            WHERE NOT EXISTS (SELECT 1 FROM resumes r WHERE r.student_id=s.id)""")).scalar()
        category = conn.execute(text("""
            SELECT coalesce(c.category,'other') AS category, count(*) AS offers
            FROM offers o JOIN companies c ON c.id=o.company_id
            GROUP BY 1 ORDER BY 2 DESC""")).mappings().all()
        top = conn.execute(text("""
            SELECT s.full_name, s.roll_no, c.name AS company, c.package
            FROM offers o JOIN students s ON s.id=o.student_id
            JOIN companies c ON c.id=o.company_id
            ORDER BY c.package DESC NULLS LAST LIMIT 10""")).mappings().all()
    students_n = overview["students"] or 1
    return {"overview": {**dict(overview),
                         "placement_rate": round(100*overview["placed"]/students_n, 1)},
            "package": dict(pkg),
            "branch_wise": [dict(r) for r in branch],
            "ctc_distribution": [dict(r) for r in ctc_dist],
            "drive_conversion": [dict(r) for r in drives],
            "round_funnel": [dict(r) for r in rounds],
            "cgpa_insight": dict(cgpa),
            "timeline": [{"month": r["month"], "offers": r["offers"]} for r in timeline],
            "action_items": {"never_applied": never_applied, "no_resume": no_resume},
            "category": [dict(r) for r in category],
            "top_offers": [dict(r) for r in top]}
