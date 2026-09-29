"""Accreditation reporting and outcome capture.

Two jobs:

  * /api/reports/*   — turn one set of rows into NAAC, NBA and NIRF answers.
  * /api/outcomes/*  — get the rows in there in the first place, which is the
                       part that actually fails at most colleges.

The arithmetic lives in app/reports.py as pure functions. This module only does
SQL and permissions, so the formulas can be tested without a database and are
auditable in one readable place.

A note on who may do what, because it is the product's whole thesis:

  Officers  read every report, record any outcome, and VERIFY.
  CRs       may collect outcomes for their own branch, unverified, if the
            officer has granted `collect_outcomes`. This is the delegation that
            makes outcome data exist at all — one TPO cannot chase 1,200
            students for admission letters — but a CR can never verify, and
            verification is what turns a claim into evidence.
  Students  self-report their own outcome and upload their own proof. Also
            unverified until the cell signs it off.

That hierarchy is not configurable at the top: no grant makes a CR able to
verify, because `collect_outcomes` and verification are different capabilities
and only the former is in CR_CAPABILITIES.
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import text

from ..attachments import MAX_ATTACHMENT_BYTES, ALLOWED_ATTACHMENT_MIMES, safe_filename
from ..auth import Claims, get_claims
from ..db import tenant_connection
from ..outcomes import count_batch, recent_batches
from ..permissions import require_cr_capability, require_placement_officer, require_staff
from ..reports import (naac_5_2_1, naac_5_2_2, naac_5_2_3,
                       nba_4_6, nirf_gms, nirf_gph, reconcile)

router = APIRouter(prefix="/api", tags=["reports"])

PLACED_KINDS = ("placed_campus", "placed_offcampus")
OUTCOME_KINDS = ("placed_campus", "placed_offcampus", "higher_studies",
                 "entrepreneurship", "competitive_exam", "not_placed", "unavailable")


# ---------------------------------------------------------------------------
# reports
# ---------------------------------------------------------------------------
@router.get("/reports/reconciliation")
def reconciliation(batch_year: int | None = None, branch_id: int | None = None,
                   claims: Claims = Depends(get_claims)):
    """All three frameworks' answers for one batch, from one set of rows.

    This is the screen that makes the case. A placement officer who files NAAC,
    NBA and NIRF has reconciled these numbers with a calculator and never been
    certain they agree — because they genuinely do not, and each is correct
    under its own definition.
    """
    require_placement_officer(claims)
    with tenant_connection(claims) as conn:
        if batch_year is None:
            recent = recent_batches(conn, 1, branch_id)
            if not recent:
                raise HTTPException(404, "No batches on record yet. Import a roster with a batch year first.")
            batch_year = recent[0]
        return reconcile(count_batch(conn, batch_year, branch_id))


@router.get("/reports/naac")
def naac_report(batch_year: int | None = None, years: int = 5,
                claims: Claims = Depends(get_claims)):
    """NAAC Criterion 5.2, year-wise.

    Five years by default, because 5.2.1/5.2.2/5.2.3 are all assessed over five
    years. A college that started keeping records this year cannot produce this
    retrospectively — which is the honest argument for starting now.
    """
    require_placement_officer(claims)
    with tenant_connection(claims) as conn:
        batches = [batch_year] if batch_year else recent_batches(conn, years, None)
        out = []
        for by in batches:
            c = count_batch(conn, by, None)
            out.append({
                "batch_year": by,
                "final_year_students": c.final_year,
                "5.2.1": naac_5_2_1(final_year=c.final_year, placed=c.placed,
                                    higher_studies=c.higher_studies),
                "5.2.2": naac_5_2_2(final_year=c.final_year,
                                    higher_studies=c.higher_studies),
                "5.2.3": naac_5_2_3(final_year=c.final_year,
                                    exam_qualified=c.exam_qualified),
                "unrecorded": c.unrecorded,
            })
    return {
        "framework": "NAAC Criterion 5.2 — Student Progression",
        "years_required": 5,
        "years_supplied": len(out),
        "complete": len(out) >= 5,
        "years": out,
        "evidence_note": ("5.2.2 requires institution, programme and proof of continuation "
                          "per student; 5.2.3 requires qualifying certificates. Upload them "
                          "against each outcome — aggregate counts alone are not submittable."),
    }


@router.get("/reports/nba")
def nba_report(branch_id: int | None = None, claims: Claims = Depends(get_claims)):
    """NBA Criterion 4.6, over the three most recent batches.

    Assessed PER PROGRAMME. Without branch_id this returns every branch
    separately, because a college with eight NBA-seeking departments files this
    eight times and a college-wide figure is not what the SAR asks for.
    """
    require_placement_officer(claims)
    with tenant_connection(claims) as conn:
        if branch_id:
            branches = conn.execute(text(
                "SELECT id, code, name FROM branches WHERE id = :b"
            ), {"b": branch_id}).mappings().all()
        else:
            branches = conn.execute(text(
                "SELECT id, code, name FROM branches ORDER BY code"
            )).mappings().all()

        programmes = []
        for b in branches:
            years = recent_batches(conn, 3, b["id"])
            batches = []
            for by in years:
                c = count_batch(conn, by, b["id"])
                batches.append({
                    "batch_year": by, "final_year": c.final_year,
                    "placed": c.placed, "higher_studies": c.higher_studies,
                    "entrepreneurship": c.entrepreneurship,
                })
            programmes.append({
                "branch_id": b["id"], "branch_code": b["code"], "branch_name": b["name"],
                **nba_4_6(batches),
            })
    return {"framework": "NBA 4.6 — Placement, Higher Studies and Entrepreneurship",
            "scope": "per programme, three batches", "programmes": programmes}


@router.get("/reports/nirf")
def nirf_report(years: int = 3, claims: Claims = Depends(get_claims)):
    """NIRF Graduation Outcomes — GPH and GMS, three-year averages.

    Worth knowing when reading this: GPH counts placement AND higher studies.
    Colleges that track only employment report the lower of the two figures they
    are entitled to. If `higher_studies` below is zero, that is far more likely
    to be missing data than a batch where nobody went on to study.
    """
    require_placement_officer(claims)
    with tenant_connection(claims) as conn:
        batches, salaries = [], {}
        for by in recent_batches(conn, years, None):
            c = count_batch(conn, by, None)
            batches.append({"batch_year": by, "final_year": c.final_year,
                            "placed": c.placed, "higher_studies": c.higher_studies})
            salaries[by] = c.salaries
    return {"framework": "NIRF Engineering — Graduation Outcomes",
            "gph": nirf_gph(batches), "gms": nirf_gms(salaries)}


# ---------------------------------------------------------------------------
# outcome capture
# ---------------------------------------------------------------------------
def _may_collect(claims: Claims, conn=None) -> None:
    """Officers always; CRs only with an explicit grant."""
    require_staff(claims)
    if claims.role == "sub_admin":
        require_cr_capability(claims, "collect_outcomes", conn)


@router.get("/outcomes")
def list_outcomes(batch_year: int | None = None, kind: str | None = None,
                  unrecorded: bool = False, claims: Claims = Depends(get_claims)):
    """Outcomes for the caller's scope. RLS confines a CR to their branch.

    `unrecorded=true` inverts the question and lists final-year students with NO
    primary outcome — the worklist that actually needs chasing, and the reason a
    college's numbers are understated.
    """
    require_staff(claims)
    with tenant_connection(claims) as conn:
        if unrecorded:
            rows = conn.execute(text("""
                SELECT s.id AS student_id, s.roll_no, s.full_name, s.email,
                       b.code AS branch, s.batch_year
                  FROM students s
                  LEFT JOIN branches b ON b.id = s.branch_id
                 WHERE (:by IS NULL OR s.batch_year = :by)
                   AND NOT EXISTS (SELECT 1 FROM student_outcomes o
                                    WHERE o.student_id = s.id AND o.is_primary)
                 ORDER BY b.code, s.roll_no LIMIT 1000
            """), {"by": batch_year}).mappings().all()
            return {"unrecorded": [dict(r) for r in rows], "count": len(rows)}

        rows = conn.execute(text("""
            SELECT o.id, o.student_id, s.roll_no, s.full_name, b.code AS branch,
                   o.batch_year, o.kind, o.is_primary, o.employer_name, o.role_title,
                   o.annual_ctc, o.institution_name, o.program_name, o.exam_name,
                   o.venture_name, o.effective_date, o.source, o.verified,
                   o.verified_at, o.notes,
                   (SELECT count(*) FROM outcome_documents d WHERE d.outcome_id = o.id) AS documents
              FROM student_outcomes o
              JOIN students s ON s.id = o.student_id
              LEFT JOIN branches b ON b.id = o.branch_id
             WHERE (:by IS NULL OR o.batch_year = :by)
               AND (:kind IS NULL OR o.kind = :kind)
             ORDER BY b.code, s.roll_no, o.is_primary DESC LIMIT 2000
        """), {"by": batch_year, "kind": kind}).mappings().all()
    return [dict(r) for r in rows]


@router.post("/outcomes")
def record_outcome(payload: dict, claims: Claims = Depends(get_claims)):
    """Record an outcome for a student.

    Never trusts the caller for `verified`: an outcome becomes evidence only
    through the verify endpoint, which is officer-only. A CR collecting fifty
    admission letters is doing the work; the officer's signature is what an
    assessor is relying on.
    """
    kind = payload.get("kind")
    if kind not in OUTCOME_KINDS:
        raise HTTPException(400, f"kind must be one of: {', '.join(OUTCOME_KINDS)}")
    student_id = payload.get("student_id")
    if not student_id:
        raise HTTPException(400, "student_id is required")

    # competitive_exam sits alongside a primary outcome rather than replacing it
    is_primary = bool(payload.get("is_primary", kind != "competitive_exam"))

    with tenant_connection(claims) as conn:
        _may_collect(claims, conn)
        st = conn.execute(text(
            "SELECT id, college_id, branch_id, batch_year FROM students WHERE id = :s"
        ), {"s": student_id}).mappings().first()
        if not st:
            raise HTTPException(404, "Student not found")

        if is_primary:
            # One headline outcome per student; replacing it is the normal case
            # (a student marked not_placed in October gets placed in December).
            conn.execute(text(
                "UPDATE student_outcomes SET is_primary = false "
                " WHERE student_id = :s AND is_primary"
            ), {"s": student_id})

        oid = conn.execute(text("""
            INSERT INTO student_outcomes
              (college_id, branch_id, student_id, batch_year, kind, is_primary,
               employer_name, role_title, company_id, annual_ctc,
               institution_name, program_name, exam_name, exam_score,
               venture_name, venture_reg_no, effective_date, source,
               verified, notes, created_by)
            VALUES
              (:col, :br, :st, :by, :kind, :prim,
               :employer, :role, :company, :ctc,
               :inst, :prog, :exam, :score,
               :venture, :vreg, :eff, :source,
               false, :notes, :uid)
            RETURNING id
        """), {
            "col": st["college_id"], "br": st["branch_id"], "st": student_id,
            "by": payload.get("batch_year") or st["batch_year"],
            "kind": kind, "prim": is_primary,
            "employer": payload.get("employer_name"), "role": payload.get("role_title"),
            "company": payload.get("company_id"), "ctc": payload.get("annual_ctc"),
            "inst": payload.get("institution_name"), "prog": payload.get("program_name"),
            "exam": payload.get("exam_name"), "score": payload.get("exam_score"),
            "venture": payload.get("venture_name"), "vreg": payload.get("venture_reg_no"),
            "eff": payload.get("effective_date"),
            "source": "officer" if claims.role in ("owner", "admin") else "officer",
            "notes": (payload.get("notes") or "")[:2000] or None,
            "uid": claims.user_id,
        }).scalar_one()
    return {"id": oid, "recorded": True, "verified": False}


@router.patch("/outcomes/{oid}/verify")
def verify_outcome(oid: int, claims: Claims = Depends(get_claims)):
    """Sign off an outcome as evidence. Officer only, by design.

    `record_offer` is already officer-only in permissions.py on the grounds that
    final outcomes are the placement officer's accountability. Verification is
    the same act for the accreditation record and carries the same restriction —
    no CR grant reaches it.
    """
    require_placement_officer(claims)
    with tenant_connection(claims) as conn:
        n = conn.execute(text("""
            UPDATE student_outcomes
               SET verified = true, verified_by = :uid, verified_at = now(),
                   updated_at = now()
             WHERE id = :o
        """), {"o": oid, "uid": claims.user_id}).rowcount
    if not n:
        raise HTTPException(404, "Outcome not found")
    return {"verified": True}


@router.post("/outcomes/{oid}/documents")
async def upload_proof(oid: int, file: UploadFile, kind: str = "proof",
                       claims: Claims = Depends(get_claims)):
    """Attach the artefact an assessor will ask for.

    NAAC 5.2.2 wants proof of continuation in higher education and 5.2.3 wants
    qualifying certificates, per student. A count without the document behind it
    is not submittable, so this is not optional decoration.
    """
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "Empty file")
    if len(raw) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(400, f"File must be under {MAX_ATTACHMENT_BYTES // (1024*1024)} MB")
    mime = file.content_type or "application/octet-stream"
    if mime not in ALLOWED_ATTACHMENT_MIMES:
        raise HTTPException(400, f"Unsupported file type: {mime}")

    with tenant_connection(claims) as conn:
        _may_collect(claims, conn)
        row = conn.execute(text(
            "SELECT id, college_id FROM student_outcomes WHERE id = :o FOR UPDATE"
        ), {"o": oid}).mappings().first()
        if not row:
            raise HTTPException(404, "Outcome not found")
        did = conn.execute(text("""
            INSERT INTO outcome_documents
              (college_id, outcome_id, kind, filename, mime, byte_size, data, uploaded_by)
            VALUES (:col, :o, :k, :fn, :m, :sz, :data, :uid) RETURNING id
        """), {
            "col": row["college_id"], "o": oid, "k": kind,
            # Forces the extension to match the stored MIME, so a file called
            # cmd.exe carrying a PDF body downloads as cmd.pdf.
            "fn": safe_filename(file.filename, mime, fallback="proof"),
            "m": mime, "sz": len(raw), "data": raw, "uid": claims.user_id,
        }).scalar_one()
    return {"id": did, "uploaded": True}


@router.get("/outcomes/{oid}/documents/{did}")
def download_proof(oid: int, did: int, claims: Claims = Depends(get_claims)):
    """Serve a proof document. RLS decides visibility, not this handler."""
    require_staff(claims)
    with tenant_connection(claims) as conn:
        row = conn.execute(text("""
            SELECT filename, mime, data FROM outcome_documents
             WHERE id = :d AND outcome_id = :o
        """), {"d": did, "o": oid}).mappings().first()
    if not row:
        raise HTTPException(404, "Document not found")
    return Response(
        content=row["data"], media_type=row["mime"],
        headers={"Content-Disposition": f'attachment; filename="{row["filename"]}"'},
    )
