"""Placement operations added in migration 0009.

Buckets, reminders, drive publish, idempotent notifications, bulk round
updates, and registration exports.

Two rules this module exists to enforce:

  * Export columns are resolved through a server-side allow-list. A column
    key never reaches SQL as an identifier, so "let the placement cell pick
    columns" cannot become "let the client read password_hash".
  * Every outbound send is idempotent. A double click, a retry or a
    reconnecting client finds the notification_log row and does nothing.
"""
from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import text

from ..auth import Claims, get_claims
from ..db import tenant_connection
from ..permissions import (require_cr_capability, require_placement_officer,
                           require_staff)

router = APIRouter(prefix="/api", tags=["placement"])

ROUNDS = [
    "resume_screening", "online_assessment", "technical_1", "technical_2",
    "technical_3", "managerial", "hr", "final_placement",
]


def _audit(conn, claims: Claims, action: str, resource_type: str,
           resource_id: int | None, detail: dict | None = None) -> None:
    """Append-only. Never raises into the caller's happy path."""
    conn.execute(text("""
        INSERT INTO audit_log (college_id, actor_user_id, actor_role, action,
                               resource_type, resource_id, detail)
        VALUES (:c, :u, :r, :a, :rt, :ri, CAST(:d AS jsonb))
    """), {"c": claims.college_id, "u": claims.user_id, "r": claims.role,
           "a": action, "rt": resource_type, "ri": resource_id,
           "d": json.dumps(detail or {})})


# ===========================================================================
# Buckets — tier1 / tier2 / dream / core, named by each college
# ===========================================================================
@router.get("/buckets")
def list_buckets(claims: Claims = Depends(get_claims)):
    require_staff(claims)
    with tenant_connection(claims) as conn:
        rows = conn.execute(text("""
            SELECT id, key, label, aliases, min_package, max_package,
                   counts_toward_cap, ignores_cap, sort_order
            FROM buckets ORDER BY sort_order, label
        """)).mappings().all()
    return [dict(r) for r in rows]


@router.put("/buckets/{bid}")
def update_bucket(bid: int, payload: dict, claims: Claims = Depends(get_claims)):
    require_placement_officer(claims)
    sets, params = [], {"b": bid}
    for field in ("label", "min_package", "max_package",
                  "counts_toward_cap", "ignores_cap", "sort_order"):
        if field in payload:
            sets.append(f"{field} = :{field}")
            params[field] = payload[field]
    if "aliases" in payload:
        aliases = payload["aliases"]
        if not isinstance(aliases, list) or any(not isinstance(a, str) for a in aliases):
            raise HTTPException(422, "Aliases must be a list of names")
        sets.append("aliases = :aliases")
        params["aliases"] = [a.strip()[:60] for a in aliases if a.strip()][:8]
    if not sets:
        raise HTTPException(400, "Nothing to update")
    with tenant_connection(claims) as conn:
        n = conn.execute(text(f"UPDATE buckets SET {', '.join(sets)} WHERE id = :b"),
                         params).rowcount
        if not n:
            raise HTTPException(404, "Bucket not found")
        _audit(conn, claims, "bucket.update", "bucket", bid, {"fields": list(params)})
    return {"updated": True}


@router.post("/buckets")
def create_bucket(payload: dict, claims: Claims = Depends(get_claims)):
    require_placement_officer(claims)
    label = (payload.get("label") or "").strip()
    if not label:
        raise HTTPException(422, "Give the bucket a name")
    key = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")[:40] or "bucket"
    with tenant_connection(claims) as conn:
        exists = conn.execute(text("SELECT 1 FROM buckets WHERE key = :k"),
                              {"k": key}).scalar()
        if exists:
            raise HTTPException(409, "A bucket with a similar name already exists")
        bid = conn.execute(text("""
            INSERT INTO buckets (college_id, key, label, min_package, max_package,
                                 counts_toward_cap, ignores_cap, sort_order)
            VALUES (:c, :k, :l, :minp, :maxp, :cap, :ign, :ord) RETURNING id
        """), {"c": claims.college_id, "k": key, "l": label[:60],
               "minp": payload.get("min_package"), "maxp": payload.get("max_package"),
               "cap": bool(payload.get("counts_toward_cap", True)),
               "ign": bool(payload.get("ignores_cap", False)),
               "ord": int(payload.get("sort_order") or 99)}).scalar_one()
        _audit(conn, claims, "bucket.create", "bucket", bid, {"label": label})
    return {"id": bid, "key": key, "created": True}


# ===========================================================================
# Reminders — private to the staff member who set them
# ===========================================================================
@router.get("/reminders")
def list_reminders(include_done: bool = False, claims: Claims = Depends(get_claims)):
    require_staff(claims)
    where = "" if include_done else "WHERE done_at IS NULL"
    with tenant_connection(claims) as conn:
        rows = conn.execute(text(f"""
            SELECT r.id, r.title, r.body, r.due_at, r.repeat_rule, r.done_at,
                   c.name AS company
            FROM reminders r
            LEFT JOIN companies c ON c.id = r.company_id
            {where}
            ORDER BY r.due_at
            LIMIT 200
        """)).mappings().all()
    return [dict(r) for r in rows]


@router.post("/reminders")
def create_reminder(payload: dict, claims: Claims = Depends(get_claims)):
    require_staff(claims)
    title = (payload.get("title") or "").strip()
    if not title:
        raise HTTPException(422, "Give the reminder a title")
    due = payload.get("due_at")
    if not due:
        raise HTTPException(422, "Choose when to be reminded")
    repeat = payload.get("repeat_rule")
    if repeat not in (None, "", "weekly", "monthly"):
        raise HTTPException(422, "Repeat must be weekly or monthly")
    with tenant_connection(claims) as conn:
        rid = conn.execute(text("""
            INSERT INTO reminders (college_id, user_id, title, body, due_at,
                                   repeat_rule, company_id)
            VALUES (:c, :u, :t, :b, :d, :rep, :co) RETURNING id
        """), {"c": claims.college_id, "u": claims.user_id, "t": title[:200],
               "b": (payload.get("body") or "")[:2000], "d": due,
               "rep": repeat or None, "co": payload.get("company_id")}).scalar_one()
    return {"id": rid, "created": True}


@router.patch("/reminders/{rid}")
def complete_reminder(rid: int, payload: dict, claims: Claims = Depends(get_claims)):
    require_staff(claims)
    done = bool(payload.get("done", True))
    with tenant_connection(claims) as conn:
        # RLS already limits this to the caller's own reminders.
        n = conn.execute(text("""
            UPDATE reminders SET done_at = CASE WHEN :d THEN now() ELSE NULL END
            WHERE id = :r
        """), {"d": done, "r": rid}).rowcount
    if not n:
        raise HTTPException(404, "Reminder not found")
    return {"updated": True}


@router.delete("/reminders/{rid}")
def delete_reminder(rid: int, claims: Claims = Depends(get_claims)):
    require_staff(claims)
    with tenant_connection(claims) as conn:
        n = conn.execute(text("DELETE FROM reminders WHERE id = :r"), {"r": rid}).rowcount
    if not n:
        raise HTTPException(404, "Reminder not found")
    return {"deleted": True}


# ===========================================================================
# Calendar — derived from drives and notes, plus the caller's reminders
# ===========================================================================
@router.get("/calendar")
def calendar(month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
             claims: Claims = Depends(get_claims)):
    require_staff(claims)
    month = month or datetime.now(timezone.utc).strftime("%Y-%m")
    start = datetime.strptime(month + "-01", "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end = (start + timedelta(days=32)).replace(day=1)
    params = {"s": start, "e": end}
    with tenant_connection(claims) as conn:
        drives = conn.execute(text("""
            SELECT id, name, deadline AS at, 'deadline' AS kind FROM companies
             WHERE deadline >= :s AND deadline < :e
            UNION ALL
            SELECT id, name, test_date AS at, 'test' AS kind FROM companies
             WHERE test_date >= :s AND test_date < :e
        """), params).mappings().all()
        notes = conn.execute(text("""
            SELECT n.id, n.title AS name, n.note_date::timestamptz AS at, n.kind
            FROM company_notes n
            WHERE n.note_date >= :s::date AND n.note_date < :e::date
        """), params).mappings().all()
        mine = conn.execute(text("""
            SELECT id, title AS name, due_at AS at, 'reminder' AS kind
            FROM reminders WHERE due_at >= :s AND due_at < :e AND done_at IS NULL
        """), params).mappings().all()
    events = [dict(r) for r in list(drives) + list(notes) + list(mine)]
    events.sort(key=lambda e: (e["at"] is None, e["at"]))
    return {"month": month, "events": events}


# ===========================================================================
# Publish a drive — the moment it becomes visible to students
# ===========================================================================
@router.post("/companies/{cid}/publish")
def publish_drive(cid: int, claims: Claims = Depends(get_claims)):
    """Distinct from a status edit: this is the audited moment a drive
    becomes visible college-wide, and the only thing that announces it."""
    require_placement_officer(claims)
    with tenant_connection(claims) as conn:
        row = conn.execute(text("""
            SELECT id, name, status, deadline FROM companies WHERE id = :c
        """), {"c": cid}).mappings().first()
        if not row:
            raise HTTPException(404, "Drive not found")
        if row["status"] == 1:
            return {"published": True, "already": True}
        if row["status"] == 2:
            raise HTTPException(409, "This drive is closed. Reopen it before publishing.")

        conn.execute(text("""
            UPDATE companies
               SET status = 1, published_at = now(), published_by = :u
             WHERE id = :c
        """), {"u": claims.user_id, "c": cid})

        group = conn.execute(text("""
            SELECT notify_groups -> 'students' ->> 'email'      AS email,
                   notify_groups -> 'students' ->> 'verified_at' AS verified_at
            FROM colleges WHERE id = :col
        """), {"col": claims.college_id}).mappings().first() or {}

        announced = False
        if group.get("email") and group.get("verified_at"):
            # Idempotent: the unique dedupe_key makes a second publish a no-op.
            announced = conn.execute(text("""
                INSERT INTO notification_log (college_id, kind, resource_type,
                                              resource_id, dedupe_key, recipients, sent_by)
                VALUES (:c, 'drive_published', 'company', :r, :k, 1, :u)
                ON CONFLICT (college_id, dedupe_key) DO NOTHING
                RETURNING id
            """), {"c": claims.college_id, "r": cid,
                   "k": f"drive_published:{cid}", "u": claims.user_id}).scalar() is not None

        _audit(conn, claims, "drive.publish", "company", cid,
               {"name": row["name"], "announced": announced})
    return {"published": True, "announced": announced,
            "group": group.get("email"), "verified": bool(group.get("verified_at"))}


@router.post("/companies/{cid}/test-reminder")
def send_test_reminder(cid: int, claims: Claims = Depends(get_claims)):
    """Email the students registered for this drive. Officer-triggered only —
    the system does not decide when a reminder is appropriate.

    Idempotent per drive per day: a second click today does nothing.
    """
    require_placement_officer(claims)
    today = datetime.now(timezone.utc).date().isoformat()
    with tenant_connection(claims) as conn:
        row = conn.execute(text("SELECT id, name, status FROM companies WHERE id = :c"),
                           {"c": cid}).mappings().first()
        if not row:
            raise HTTPException(404, "Drive not found")
        if row["status"] != 1:
            raise HTTPException(409, "Publish the drive before reminding students")

        n = conn.execute(text("""
            SELECT count(*) FROM applications
             WHERE company_id = :c AND status = 'active'
        """), {"c": cid}).scalar() or 0
        if not n:
            raise HTTPException(409, "Nobody is registered for this drive yet")

        sent = conn.execute(text("""
            INSERT INTO notification_log (college_id, kind, resource_type,
                                          resource_id, dedupe_key, recipients, sent_by)
            VALUES (:c, 'test_reminder', 'company', :r, :k, :n, :u)
            ON CONFLICT (college_id, dedupe_key) DO NOTHING
            RETURNING id
        """), {"c": claims.college_id, "r": cid,
               "k": f"test_reminder:{cid}:{today}", "n": n,
               "u": claims.user_id}).scalar()
        if sent is None:
            return {"sent": False, "already_sent_today": True, "recipients": n}
        _audit(conn, claims, "drive.test_reminder", "company", cid, {"recipients": n})
    return {"sent": True, "recipients": n}


@router.get("/companies/{cid}/notifications")
def drive_notifications(cid: int, claims: Claims = Depends(get_claims)):
    require_staff(claims)
    with tenant_connection(claims) as conn:
        rows = conn.execute(text("""
            SELECT kind, recipients, sent_at FROM notification_log
             WHERE resource_type = 'company' AND resource_id = :c
             ORDER BY sent_at DESC LIMIT 50
        """), {"c": cid}).mappings().all()
    return [dict(r) for r in rows]


# ===========================================================================
# Bulk round updates
# ===========================================================================
@router.patch("/applications/bulk")
def bulk_update(payload: dict, claims: Claims = Depends(get_claims)):
    """Move many candidates at once. One transaction, one audit row.

    A CR may move rounds (with the capability) but may never set a final
    status — that restriction matches the single-record endpoint.
    """
    require_cr_capability(claims, "manage_branch_pipeline")
    ids = payload.get("ids")
    if not isinstance(ids, list) or not ids:
        raise HTTPException(422, "Select at least one student")
    if len(ids) > 500:
        raise HTTPException(422, "Select at most 500 students at a time")
    try:
        ids = [int(i) for i in ids]
    except (TypeError, ValueError):
        raise HTTPException(422, "Invalid selection")

    rnd = payload.get("current_round")
    status = payload.get("status")
    if not rnd and not status:
        raise HTTPException(422, "Choose a round or an outcome")
    if rnd and rnd not in ROUNDS:
        raise HTTPException(422, "Unknown round")
    if status and status not in ("active", "placed", "rejected", "withdrawn", "absent"):
        raise HTTPException(422, "Unknown outcome")
    if status is not None and claims.role == "sub_admin":
        raise HTTPException(
            403,
            "CRs can update interview rounds, but only the placement officer "
            "can record a final outcome")

    sets, params = [], {"ids": ids}
    if rnd:
        sets.append("current_round = :r")
        params["r"] = rnd
    if status:
        sets.append("status = :s")
        params["s"] = status

    with tenant_connection(claims) as conn:
        # RLS scopes this to the caller's college, and to their branch for a CR.
        rows = conn.execute(text(f"""
            UPDATE applications SET {', '.join(sets)}
             WHERE id = ANY(:ids)
            RETURNING id, college_id, student_id, company_id
        """), params).mappings().all()
        if not rows:
            raise HTTPException(404, "None of those applications are yours to update")

        if rnd:
            for r in rows:
                conn.execute(text("""
                    INSERT INTO round_progress (college_id, application_id, round,
                                                status, actor_user_id, updated_at)
                    VALUES (:c, :a, :r, :st, :u, now())
                    ON CONFLICT (application_id, round)
                    DO UPDATE SET status = EXCLUDED.status,
                                  actor_user_id = EXCLUDED.actor_user_id,
                                  updated_at = now()
                """), {"c": r["college_id"], "a": r["id"], "r": rnd,
                       "st": "cleared" if status != "rejected" else "failed",
                       "u": claims.user_id})

        if status == "placed":
            for r in rows:
                conn.execute(text("""
                    INSERT INTO offers (college_id, student_id, company_id, category)
                    SELECT :col, :st, :co, c.category FROM companies c WHERE c.id = :co
                    ON CONFLICT DO NOTHING
                """), {"col": r["college_id"], "st": r["student_id"], "co": r["company_id"]})

        _audit(conn, claims, "applications.bulk_update", "company",
               rows[0]["company_id"],
               {"count": len(rows), "round": rnd, "status": status})
    return {"updated": len(rows)}


# ===========================================================================
# Registration export
# ===========================================================================
# The allow-list. A key the client sends maps to an expression HERE, or it
# does not exist. Client input is never interpolated into SQL.
EXPORT_COLUMNS: dict[str, tuple[str, str]] = {
    "roll_no":       ("s.roll_no",                          "Roll number"),
    "full_name":     ("s.full_name",                        "Name"),
    "branch":        ("b.code",                             "Branch"),
    "email":         ("s.email",                            "Email"),
    "cgpa":          ("s.cgpa::text",                       "CGPA"),
    "backlogs":      ("s.backlogs::text",                   "Backlogs"),
    "verified":      ("s.verified::text",                   "Verified"),
    "tenth_pct":     ("s.attributes->>'tenth_pct'",         "10th %"),
    "twelfth_pct":   ("s.attributes->>'twelfth_pct'",       "12th %"),
    "phone":         ("s.attributes->>'phone'",             "Phone"),
    "gender":        ("s.attributes->>'gender'",            "Gender"),
    "current_round": ("a.current_round",                    "Round"),
    "status":        ("a.status",                           "Status"),
    "applied_at":    ("to_char(a.created_at,'YYYY-MM-DD')", "Applied on"),
    "has_resume":    ("(r.id IS NOT NULL)::text",           "Resume on file"),
}
DEFAULT_SHORT = ["roll_no", "full_name", "branch", "email", "cgpa"]


def _safe_slug(value: str, fallback: str = "drive") -> str:
    """Company names are typed by humans and end up in a filename."""
    slug = re.sub(r"[^A-Za-z0-9]+", "-", (value or "")).strip("-")[:60]
    return slug or fallback


@router.get("/export/columns")
def export_columns(claims: Claims = Depends(get_claims)):
    require_staff(claims)
    with tenant_connection(claims) as conn:
        templates = conn.execute(text("""
            SELECT id, name, columns, is_default FROM export_templates ORDER BY name
        """)).mappings().all()
    return {
        "columns": [{"key": k, "label": v[1]} for k, v in EXPORT_COLUMNS.items()],
        "templates": [dict(t) for t in templates],
    }


@router.post("/export/templates")
def save_template(payload: dict, claims: Claims = Depends(get_claims)):
    require_placement_officer(claims)
    name = (payload.get("name") or "").strip()
    cols = payload.get("columns")
    if not name:
        raise HTTPException(422, "Name this column set")
    if not isinstance(cols, list) or not cols:
        raise HTTPException(422, "Choose at least one column")
    unknown = [c for c in cols if c not in EXPORT_COLUMNS]
    if unknown:
        raise HTTPException(422, f"Unknown column: {unknown[0]}")
    with tenant_connection(claims) as conn:
        conn.execute(text("""
            INSERT INTO export_templates (college_id, name, columns, created_by)
            VALUES (:c, :n, CAST(:j AS jsonb), :u)
            ON CONFLICT (college_id, name)
            DO UPDATE SET columns = EXCLUDED.columns
        """), {"c": claims.college_id, "n": name[:60],
               "j": json.dumps(list(dict.fromkeys(cols))[:30]), "u": claims.user_id})
    return {"saved": True}


@router.get("/companies/{cid}/export")
def export_registrations(cid: int,
                         cols: str | None = Query(None, max_length=600),
                         claims: Claims = Depends(get_claims)):
    """Registration sheet as CSV. Opens directly in Excel.

    `cols` is a comma-separated list of allow-listed keys. Anything not in
    EXPORT_COLUMNS is rejected rather than ignored, so a typo is visible
    instead of silently producing a sheet with a missing column.
    """
    require_cr_capability(claims, "export_registrations")

    keys = [c.strip() for c in cols.split(",")] if cols else DEFAULT_SHORT
    keys = [k for k in dict.fromkeys(keys) if k]
    if not keys:
        raise HTTPException(422, "Choose at least one column")
    unknown = [k for k in keys if k not in EXPORT_COLUMNS]
    if unknown:
        raise HTTPException(422, f"Unknown column: {unknown[0]}")
    if len(keys) > 30:
        raise HTTPException(422, "Too many columns")

    select = ", ".join(f"{EXPORT_COLUMNS[k][0]} AS col_{i}" for i, k in enumerate(keys))
    with tenant_connection(claims) as conn:
        drive = conn.execute(text("SELECT name, test_date FROM companies WHERE id = :c"),
                             {"c": cid}).mappings().first()
        if not drive:
            raise HTTPException(404, "Drive not found")
        rows = conn.execute(text(f"""
            SELECT {select}
            FROM applications a
            JOIN students s ON s.id = a.student_id
            JOIN branches b ON b.id = a.branch_id
            LEFT JOIN resumes r ON r.student_id = s.id
            WHERE a.company_id = :c
            ORDER BY s.roll_no
        """), {"c": cid}).all()
        _audit(conn, claims, "registrations.export", "company", cid,
               {"columns": keys, "rows": len(rows)})

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([EXPORT_COLUMNS[k][1] for k in keys])
    for row in rows:
        writer.writerow(["" if v is None else v for v in row])
    buf.seek(0)

    when = (drive["test_date"] or datetime.now(timezone.utc)).strftime("%Y-%m-%d")
    filename = f"{_safe_slug(drive['name'], 'drive')}_{when}_registrations.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/companies/{cid}/resumes")
def export_resumes(cid: int, cleared_only: bool = False,
                   claims: Claims = Depends(get_claims)):
    """Every registrant's resume as one zip, foldered by company and date.

    Officer-only, scoped strictly to this drive's registrants, and audited.
    Resumes currently live in Postgres as bytea (see ADR-06); this streams
    them out one at a time rather than holding the whole archive in memory.
    """
    import zipfile

    require_placement_officer(claims)
    with tenant_connection(claims) as conn:
        drive = conn.execute(text("SELECT name, test_date FROM companies WHERE id = :c"),
                             {"c": cid}).mappings().first()
        if not drive:
            raise HTTPException(404, "Drive not found")
        cleared = "AND a.status <> 'rejected'" if cleared_only else ""
        rows = conn.execute(text(f"""
            SELECT s.roll_no, s.full_name, r.filename, r.data
            FROM applications a
            JOIN students s ON s.id = a.student_id
            LEFT JOIN resumes r ON r.student_id = s.id
            WHERE a.company_id = :c {cleared}
            ORDER BY s.roll_no
        """), {"c": cid}).mappings().all()
        _audit(conn, claims, "resumes.export", "company", cid,
               {"students": len(rows), "cleared_only": cleared_only})

    when = (drive["test_date"] or datetime.now(timezone.utc)).strftime("%Y-%m-%d")
    folder = f"{_safe_slug(drive['name'], 'drive')}_{when}"

    buf = io.BytesIO()
    missing = []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for row in rows:
            if not row["data"]:
                missing.append(f"{row['roll_no']}  {row['full_name'] or ''}".strip())
                continue
            safe = _safe_slug(row["roll_no"], "student")
            z.writestr(f"{folder}/{safe}.pdf", bytes(row["data"]))
        if missing:
            z.writestr(f"{folder}/missing.txt",
                       "These students registered but have no resume on file:\n\n"
                       + "\n".join(missing) + "\n")
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{folder}.zip"'},
    )


# ===========================================================================
# Drive details the original PATCH /companies/{id} does not accept
# ===========================================================================
@router.patch("/companies/{cid}/details")
def update_drive_details(cid: int, payload: dict, claims: Claims = Depends(get_claims)):
    """Role, test date, venue and the plain-language restriction note.

    Kept separate from PATCH /companies/{id} so the original allow-list
    there stays untouched.
    """
    require_placement_officer(claims)
    sets, params = [], {"c": cid}
    for field in ("role_title", "venue", "restriction_note"):
        if field in payload:
            sets.append(f"{field} = :{field}")
            params[field] = (payload[field] or None)
    if "test_date" in payload:
        sets.append("test_date = :test_date")
        params["test_date"] = payload["test_date"] or None
    if "custom_policy" in payload:
        cp = payload["custom_policy"]
        if cp is not None and not isinstance(cp, dict):
            raise HTTPException(422, "Custom policy must be an object")
        sets.append("custom_policy = CAST(:custom_policy AS jsonb)")
        params["custom_policy"] = json.dumps(cp) if cp else None
    if not sets:
        raise HTTPException(400, "Nothing to update")
    with tenant_connection(claims) as conn:
        n = conn.execute(text(f"UPDATE companies SET {', '.join(sets)} WHERE id = :c"),
                         params).rowcount
        if not n:
            raise HTTPException(404, "Drive not found")
        _audit(conn, claims, "drive.update_details", "company", cid,
               {"fields": [k for k in params if k != "c"]})
    return {"updated": True}


@router.get("/companies/{cid}/details")
def drive_details(cid: int, claims: Claims = Depends(get_claims)):
    require_staff(claims)
    with tenant_connection(claims) as conn:
        row = conn.execute(text("""
            SELECT id, name, category, package, status, deadline, role_title,
                   test_date, venue, restriction_note, custom_policy,
                   eligible_branches, min_cgpa, max_backlogs, eligibility_rules,
                   published_at
            FROM companies WHERE id = :c
        """), {"c": cid}).mappings().first()
    if not row:
        raise HTTPException(404, "Drive not found")
    return dict(row)


# ===========================================================================
# Who am I, for the student portal
# ===========================================================================
@router.get("/me/context")
def my_context(claims: Claims = Depends(get_claims)):
    """Final-year or junior, plus the college's display name.

    A junior is a student in a non-final year — not a separate role, so
    this is a derived flag rather than anything in the JWT.
    """
    if claims.role not in ("student", "alumni"):
        return {"is_final_year": True, "batch_year": None}
    with tenant_connection(claims) as conn:
        row = conn.execute(text("""
            SELECT s.batch_year, is_final_year(s.batch_year) AS final
            FROM students s WHERE s.user_id = :u
        """), {"u": claims.user_id}).mappings().first()
    if not row:
        return {"is_final_year": True, "batch_year": None}
    return {"is_final_year": bool(row["final"]), "batch_year": row["batch_year"]}


# ===========================================================================
# Entitlements — what this college has bought. Read-only from the app.
# ===========================================================================
@router.get("/entitlements")
def entitlements(claims: Claims = Depends(get_claims)):
    if not claims.college_id and claims.role != "owner":
        raise HTTPException(403, "No college scope on this account")
    with tenant_connection(claims) as conn:
        rows = conn.execute(text("SELECT feature, enabled FROM entitlements")).all()
    return {feature: enabled for feature, enabled in rows}
