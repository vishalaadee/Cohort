"""Roster management for admins.

CSV import is the onboarding backbone for every college, and the ONLY path
for colleges whose students don't have Google accounts. Expected header:

    roll_no,email,full_name,branch_code,cgpa,backlogs[,activation_code]

Behaviour, chosen for painless onboarding:
  * validated per row — bad rows are reported with line numbers, good rows import
  * unknown branch codes auto-create the branch (reported back)
  * duplicate roll numbers within the college are skipped, not errors
  * every imported student gets an activation code (from the file if supplied,
    generated otherwise) — returned once in the response for the admin to
    distribute; also retrievable later via the codes endpoint
"""
import csv
import io
import secrets

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import text

from ..auth import Claims, get_claims
from ..db import tenant_connection

router = APIRouter(prefix="/api/admin", tags=["admin"])

REQUIRED_COLS = {"roll_no", "email", "full_name", "branch_code"}
MAX_ROWS = 5000


def _require_staff(claims: Claims):
    if claims.role not in ("owner", "admin", "sub_admin"):
        raise HTTPException(403, "Placement-cell access required")
    if claims.role != "owner" and not claims.college_id:
        raise HTTPException(403, "No college scope on this account")


@router.post("/students/import")
async def import_students(file: UploadFile, claims: Claims = Depends(get_claims)):
    _require_staff(claims)
    if claims.role == "sub_admin":
        raise HTTPException(403, "Only the placement officer (admin) can import the roster")

    raw = await file.read()
    try:
        textdata = raw.decode("utf-8-sig")  # tolerate Excel's BOM
    except UnicodeDecodeError:
        raise HTTPException(400, "File must be UTF-8 CSV (export from Excel/Sheets as CSV)")

    reader = csv.DictReader(io.StringIO(textdata))
    if not reader.fieldnames:
        raise HTTPException(400, "Empty file")
    cols = {c.strip().lower() for c in reader.fieldnames}
    missing = REQUIRED_COLS - cols
    if missing:
        raise HTTPException(400, f"Missing required columns: {', '.join(sorted(missing))}")

    imported, skipped, errors, codes = 0, 0, [], []
    created_branches: list[str] = []

    with tenant_connection(claims) as conn:
        cid = claims.college_id
        branch_ids = dict(conn.execute(text(
            "SELECT upper(code), id FROM branches WHERE college_id = :cid"
        ), {"cid": cid}).all())
        existing_rolls = {r[0].upper() for r in conn.execute(text(
            "SELECT roll_no FROM students WHERE college_id = :cid"
        ), {"cid": cid}).all()}

        for i, row in enumerate(reader, start=2):  # row 1 is the header
            if i - 1 > MAX_ROWS:
                errors.append({"row": i, "error": f"File exceeds {MAX_ROWS} rows; split it"})
                break
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
            roll = row.get("roll_no", "")
            email = row.get("email", "").lower()
            name = row.get("full_name", "")
            bcode = row.get("branch_code", "").upper()

            if not roll or not name or not bcode:
                errors.append({"row": i, "error": "roll_no, full_name and branch_code are required"}); continue
            if "@" not in email or "." not in email.split("@")[-1]:
                errors.append({"row": i, "error": f"invalid email '{row.get('email','')}'"}); continue
            if roll.upper() in existing_rolls:
                skipped += 1; continue

            try:
                cgpa = round(float(row["cgpa"]), 2) if row.get("cgpa") else None
                if cgpa is not None and not (0 <= cgpa <= 10):
                    raise ValueError
            except ValueError:
                errors.append({"row": i, "error": f"cgpa '{row.get('cgpa')}' must be a number 0–10"}); continue
            try:
                backlogs = int(row["backlogs"]) if row.get("backlogs") else 0
                if backlogs < 0:
                    raise ValueError
            except ValueError:
                errors.append({"row": i, "error": f"backlogs '{row.get('backlogs')}' must be a whole number"}); continue

            if bcode not in branch_ids:
                bid = conn.execute(text("""
                    INSERT INTO branches (college_id, code, name)
                    VALUES (:cid, :code, :code) RETURNING id
                """), {"cid": cid, "code": bcode}).scalar_one()
                branch_ids[bcode] = bid
                created_branches.append(bcode)

            code = (row.get("activation_code") or secrets.token_hex(4)).upper()
            conn.execute(text("""
                INSERT INTO students (college_id, branch_id, roll_no, email, full_name,
                                      cgpa, backlogs, activation_code)
                VALUES (:cid, :bid, :roll, :email, :name, :cgpa, :backlogs, :code)
            """), {"cid": cid, "bid": branch_ids[bcode], "roll": roll, "email": email,
                   "name": name, "cgpa": cgpa, "backlogs": backlogs, "code": code})
            existing_rolls.add(roll.upper())
            codes.append({"roll_no": roll, "full_name": name, "email": email,
                          "activation_code": code})
            imported += 1

    return {"imported": imported, "skipped_existing": skipped,
            "created_branches": created_branches, "errors": errors,
            "activation_codes": codes}


@router.get("/students/activation-codes")
def unclaimed_codes(claims: Claims = Depends(get_claims)):
    """Codes for students who haven't claimed yet — for (re)distribution."""
    _require_staff(claims)
    with tenant_connection(claims) as conn:
        rows = conn.execute(text("""
            SELECT s.roll_no, s.full_name, s.email, s.activation_code, b.code AS branch
            FROM students s JOIN branches b ON b.id = s.branch_id
            WHERE s.user_id IS NULL AND s.activation_code IS NOT NULL
            ORDER BY b.code, s.roll_no
        """)).mappings().all()
    return [dict(r) for r in rows]


@router.get("/students")
def list_students(q: str | None = None, claims: Claims = Depends(get_claims)):
    """Tenant-scoped roster. RLS trims this to the caller's college (admin)
    or branch (sub_admin) automatically."""
    _require_staff(claims)
    where, params = "", {}
    if q:
        where = "WHERE s.roll_no ILIKE :q OR s.full_name ILIKE :q OR s.email ILIKE :q"
        params["q"] = f"%{q}%"
    with tenant_connection(claims) as conn:
        rows = conn.execute(text(f"""
            SELECT s.id, s.roll_no, s.full_name, s.email, s.cgpa, s.backlogs,
                   b.code AS branch, s.verified,
                   (s.user_id IS NOT NULL) AS has_login
            FROM students s JOIN branches b ON b.id = s.branch_id
            {where}
            ORDER BY s.roll_no
            LIMIT 500
        """), params).mappings().all()
    return [dict(r) for r in rows]
