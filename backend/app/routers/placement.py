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

from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import text

from .. import mailer
from ..attachments import (ALLOWED_ATTACHMENT_MIMES, ATTACHMENT_KINDS,
                           MAX_ATTACHMENT_BYTES, MAX_ATTACHMENTS_PER_DRIVE,
                           safe_filename)
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
    # The Query pattern accepts any two digits, so "2026-13" and "2026-00" get
    # through it and reach strptime, which raises ValueError -> 500. Now that
    # the planner actually sends this parameter, turn that into a 422.
    try:
        start = datetime.strptime(month + "-01", "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        raise HTTPException(422, f"{month} is not a real month")
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
            SELECT name AS college_name,
                   notify_groups -> 'students' ->> 'email'       AS email,
                   notify_groups -> 'students' ->> 'verified_at' AS verified_at
            FROM colleges WHERE id = :col
        """), {"col": claims.college_id}).mappings().first() or {}

        announced, mail_status, mail_error = False, None, None

        if group.get("email") and group.get("verified_at"):
            # Idempotent: the unique dedupe_key makes a second publish a no-op.
            notif_id = conn.execute(text("""
                INSERT INTO notification_log (college_id, kind, resource_type,
                                              resource_id, dedupe_key, recipients, sent_by)
                VALUES (:c, 'drive_published', 'company', :r, :k, 1, :u)
                ON CONFLICT (college_id, dedupe_key) DO NOTHING
                RETURNING id
            """), {"c": claims.college_id, "r": cid,
                   "k": f"drive_published:{cid}", "u": claims.user_id}).scalar()

            if notif_id is not None:
                result = _send_drive_announcement(
                    conn, claims, cid, group["email"],
                    group.get("college_name") or "Your college")
                mailer.record(conn, claims, result, notif_id)
                mail_status, mail_error = result.status, result.error

                if result.ok:
                    announced = True
                else:
                    # The send failed, so drop the dedupe row. Otherwise the
                    # log says "announced" forever and pressing Publish again
                    # — the obvious thing to try — would do nothing at all.
                    # The drive stays published: that part did work.
                    conn.execute(text("DELETE FROM notification_log WHERE id = :n"),
                                 {"n": notif_id})
            else:
                announced, mail_status = True, "already_sent"

        _audit(conn, claims, "drive.publish", "company", cid,
               {"name": row["name"], "announced": announced,
                "mail_status": mail_status})

    return {"published": True, "announced": announced,
            "group": group.get("email"), "verified": bool(group.get("verified_at")),
            "mail_status": mail_status, "mail_error": mail_error}


def _send_drive_announcement(conn, claims: Claims, cid: int,
                             to_address: str, college_name: str):
    """Build and send the announcement for a drive, JDs attached.

    Split out of publish_drive so the retry endpoint below sends exactly the
    same message rather than a second, subtly different implementation of it.
    """
    drive = conn.execute(text("""
        SELECT c.name, c.role_title, c.package, c.deadline, c.test_date,
               c.venue, c.restriction_note, b.label AS bucket_label
          FROM companies c
          LEFT JOIN buckets b ON b.college_id = c.college_id AND b.key = c.category
         WHERE c.id = :c
    """), {"c": cid}).mappings().first() or {}

    files = conn.execute(text("""
        SELECT filename, mime, data FROM drive_attachments
         WHERE company_id = :c ORDER BY created_at
    """), {"c": cid}).mappings().all()

    attachments = [mailer.Attachment(filename=f["filename"], mime=f["mime"],
                                     data=bytes(f["data"])) for f in files]

    portal_url = str(mailer.conf("PORTAL_URL", "") or "").rstrip("/") + "/app"
    subject, text_body, html = mailer.drive_announcement(
        dict(drive), college_name, portal_url, attachments)
    return mailer.send_mail(to_address, subject, text_body, html, attachments)


@router.post("/companies/{cid}/resend-announcement")
def resend_announcement(cid: int, claims: Claims = Depends(get_claims)):
    """Send the announcement again — after a failed send, or after attaching a
    JD that missed the original.

    Not idempotent, by design: the officer is explicitly asking to send again,
    and the only reason to be here is that the first attempt didn't land. It is
    audited, and the mail_log shows every send, so 'who mailed the group twice'
    always has an answer.
    """
    require_placement_officer(claims)
    with tenant_connection(claims) as conn:
        row = conn.execute(text("SELECT id, name, status FROM companies WHERE id = :c"),
                           {"c": cid}).mappings().first()
        if not row:
            raise HTTPException(404, "Drive not found")
        if row["status"] != 1:
            raise HTTPException(409, "Publish the drive before announcing it")

        group = conn.execute(text("""
            SELECT name AS college_name,
                   notify_groups -> 'students' ->> 'email'       AS email,
                   notify_groups -> 'students' ->> 'verified_at' AS verified_at
            FROM colleges WHERE id = :col
        """), {"col": claims.college_id}).mappings().first() or {}

        if not group.get("email"):
            raise HTTPException(409, "No student group address is set")
        if not group.get("verified_at"):
            raise HTTPException(409, "The student group address is not confirmed yet")

        result = _send_drive_announcement(
            conn, claims, cid, group["email"],
            group.get("college_name") or "Your college")
        mailer.record(conn, claims, result)
        _audit(conn, claims, "drive.announcement_resend", "company", cid,
               {"status": result.status, "to": group["email"]})

    if result.status == "skipped":
        raise HTTPException(503, result.error or "Email is not configured on this server")
    if result.status == "failed":
        raise HTTPException(502, result.error or "The mail server rejected the message")
    return {"sent": True, "to": group["email"], "attachments": result.attachments}


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


# ===========================================================================
# Drive attachments — the JD and up to two companions
#
# Limits, the MIME allow-list and filename handling live in ../attachments.py
# because portal.py serves the student's download of the same file and the two
# must agree on what it is called.
# ===========================================================================
def _attachment_rows(conn, cid: int):
    return conn.execute(text("""
        SELECT id, kind, filename, mime, byte_size, created_at
          FROM drive_attachments
         WHERE company_id = :c
         ORDER BY created_at
    """), {"c": cid}).mappings().all()


@router.get("/companies/{cid}/attachments")
def list_attachments(cid: int, claims: Claims = Depends(get_claims)):
    """Metadata only — never the bytes. Staff see attachments on any drive."""
    require_staff(claims)
    with tenant_connection(claims) as conn:
        rows = _attachment_rows(conn, cid)
    return [dict(r) for r in rows]


@router.post("/companies/{cid}/attachments")
async def upload_attachment(cid: int,
                            file: UploadFile,
                            kind: str = Query("jd"),
                            claims: Claims = Depends(get_claims)):
    """Attach a JD (or form/brochure) to a drive. Officer only.

    Deliberately not a CR capability: an attachment goes out by email to the
    whole college on publish, which makes it an announcement, and announcing
    is officer-only everywhere else in this module.
    """
    require_placement_officer(claims)

    if kind not in ATTACHMENT_KINDS:
        raise HTTPException(422, f"kind must be one of: {', '.join(sorted(ATTACHMENT_KINDS))}")

    mime = (file.content_type or "").split(";")[0].strip().lower()
    if mime not in ALLOWED_ATTACHMENT_MIMES:
        raise HTTPException(
            422, "Attach a PDF, Word document or image. "
                 f"That file is {mime or 'of an unknown type'}.")

    data = await file.read()
    if not data:
        raise HTTPException(422, "That file is empty")
    if len(data) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(
            422, f"{file.filename} is {len(data) // 1024 // 1024} MB. "
                 f"The limit is {MAX_ATTACHMENT_BYTES // 1024 // 1024} MB per file.")

    filename = (file.filename or "attachment").strip()[:200]

    with tenant_connection(claims) as conn:
        # FOR UPDATE locks this drive's row for the rest of the transaction, so
        # two uploads to the same drive queue instead of racing. Without it both
        # can read count = 2, both pass the check, and the drive ends up with
        # four attachments — the cap is checked and written non-atomically.
        # Locking the parent is the cheapest way to serialise; it blocks only
        # concurrent writers to this one drive.
        drive = conn.execute(
            text("SELECT id, name, status FROM companies WHERE id = :c FOR UPDATE"),
            {"c": cid}).mappings().first()
        if not drive:
            raise HTTPException(404, "Drive not found")

        count = conn.execute(text(
            "SELECT count(*) FROM drive_attachments WHERE company_id = :c"),
            {"c": cid}).scalar() or 0
        if count >= MAX_ATTACHMENTS_PER_DRIVE:
            raise HTTPException(
                409, f"This drive already has {MAX_ATTACHMENTS_PER_DRIVE} attachments. "
                     "Remove one before adding another.")

        aid = conn.execute(text("""
            INSERT INTO drive_attachments (college_id, company_id, kind, filename,
                                           mime, byte_size, data, uploaded_by)
            VALUES (:col, :c, :k, :f, :m, :s, :d, :u)
            RETURNING id
        """), {"col": claims.college_id, "c": cid, "k": kind, "f": filename,
               "m": mime, "s": len(data), "d": data, "u": claims.user_id}).scalar()

        _audit(conn, claims, "drive.attachment_add", "company", cid,
               {"attachment_id": aid, "filename": filename,
                "kind": kind, "bytes": len(data)})

        # Published already? Then this file missed the announcement email.
        # Say so rather than letting the officer assume students have it.
        late = drive["status"] == 1

    return {"id": aid, "filename": filename, "kind": kind,
            "byte_size": len(data), "slots_left": MAX_ATTACHMENTS_PER_DRIVE - count - 1,
            "after_publish": late}


@router.get("/companies/{cid}/attachments/{aid}/download")
def download_attachment(cid: int, aid: int, claims: Claims = Depends(get_claims)):
    """Staff download. The student-facing equivalent lives in portal.py, where
    the published-status check belongs."""
    require_staff(claims)
    with tenant_connection(claims) as conn:
        row = conn.execute(text("""
            SELECT filename, mime, data FROM drive_attachments
             WHERE id = :a AND company_id = :c
        """), {"a": aid, "c": cid}).mappings().first()
    if not row:
        raise HTTPException(404, "Attachment not found")
    return Response(
        content=row["data"], media_type=row["mime"],
        headers={"Content-Disposition":
                 f'attachment; filename="{safe_filename(row["filename"], row["mime"])}"'})


@router.delete("/companies/{cid}/attachments/{aid}")
def delete_attachment(cid: int, aid: int, claims: Claims = Depends(get_claims)):
    require_placement_officer(claims)
    with tenant_connection(claims) as conn:
        row = conn.execute(text("""
            DELETE FROM drive_attachments
             WHERE id = :a AND company_id = :c
            RETURNING filename
        """), {"a": aid, "c": cid}).mappings().first()
        if not row:
            raise HTTPException(404, "Attachment not found")
        _audit(conn, claims, "drive.attachment_remove", "company", cid,
               {"attachment_id": aid, "filename": row["filename"]})
    return {"deleted": True, "filename": row["filename"]}


# ===========================================================================
# Announcement group addresses — officer-only, and verified before use
# ===========================================================================
GROUP_KEYS = {"students": "final-year students", "juniors": "juniors"}
VERIFICATION_VALID_HOURS = 48


@router.get("/notify-groups")
def get_notify_groups(claims: Claims = Depends(get_claims)):
    """The two addresses announcements can go to, and whether each is verified."""
    require_staff(claims)
    with tenant_connection(claims) as conn:
        raw = conn.execute(text("SELECT notify_groups FROM colleges WHERE id = :c"),
                           {"c": claims.college_id}).scalar() or {}
    if isinstance(raw, str):
        raw = json.loads(raw)
    out = {}
    for key, label in GROUP_KEYS.items():
        entry = raw.get(key) or {}
        out[key] = {"label": label,
                    "email": entry.get("email"),
                    "verified": bool(entry.get("verified_at")),
                    "verified_at": entry.get("verified_at")}
    return out


@router.put("/notify-groups")
def set_notify_groups(payload: dict, claims: Claims = Depends(get_claims)):
    """Set one or both group addresses. Placement officer only.

    Changing an address clears its verification. That is the whole point: an
    account that has been taken over could otherwise point every future
    announcement at an outside address, and nothing downstream would notice
    because the address was verified once, months ago, when it was different.
    """
    require_placement_officer(claims)

    updates = {k: v for k, v in payload.items() if k in GROUP_KEYS}
    if not updates:
        raise HTTPException(422, f"Send one or both of: {', '.join(GROUP_KEYS)}")

    with tenant_connection(claims) as conn:
        raw = conn.execute(text("SELECT notify_groups FROM colleges WHERE id = :c"),
                           {"c": claims.college_id}).scalar() or {}
        if isinstance(raw, str):
            raw = json.loads(raw)
        groups = dict(raw)
        changed = []

        for key, value in updates.items():
            email = (value or "").strip().lower() if isinstance(value, str) else \
                    (value or {}).get("email", "").strip().lower()

            if not email:
                groups.pop(key, None)
                changed.append({"group": key, "email": None, "action": "cleared"})
                continue

            if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", email):
                raise HTTPException(422, f"{email} is not a valid email address")

            existing = groups.get(key) or {}
            if existing.get("email") == email:
                continue                       # no change, keep verification
            groups[key] = {"email": email, "verified_at": None}
            changed.append({"group": key, "email": email, "action": "set"})

        if not changed:
            return {"changed": False, **{k: groups.get(k) for k in GROUP_KEYS}}

        conn.execute(text("UPDATE colleges SET notify_groups = CAST(:g AS jsonb) WHERE id = :c"),
                     {"g": json.dumps(groups), "c": claims.college_id})
        _audit(conn, claims, "college.notify_groups_set", "college",
               claims.college_id, {"changed": changed})

    return {"changed": True,
            **{k: {"email": (groups.get(k) or {}).get("email"),
                   "verified": bool((groups.get(k) or {}).get("verified_at"))}
               for k in GROUP_KEYS}}


@router.post("/notify-groups/{key}/send-verification")
def send_group_verification(key: str, claims: Claims = Depends(get_claims)):
    """Mail a confirmation link to the group address itself.

    Whoever receives mail at that address confirms it. An officer typing an
    address is a claim; a click from inside that mailbox is evidence.
    """
    require_placement_officer(claims)
    if key not in GROUP_KEYS:
        raise HTTPException(404, "No such group")

    import secrets
    from .. import mailer

    with tenant_connection(claims) as conn:
        row = conn.execute(text("""
            SELECT name, notify_groups FROM colleges WHERE id = :c
        """), {"c": claims.college_id}).mappings().first()
        raw = row["notify_groups"] or {}
        if isinstance(raw, str):
            raw = json.loads(raw)
        entry = raw.get(key) or {}
        email = entry.get("email")
        if not email:
            raise HTTPException(409, f"Set the {GROUP_KEYS[key]} address first")
        if entry.get("verified_at"):
            return {"sent": False, "already_verified": True, "email": email}

        token = secrets.token_urlsafe(32)
        conn.execute(text("""
            INSERT INTO group_verifications (college_id, group_key, email, token,
                                             expires_at, created_by)
            VALUES (:c, :k, :e, :t, now() + make_interval(hours => :h), :u)
        """), {"c": claims.college_id, "k": key, "e": email, "t": token,
               "h": VERIFICATION_VALID_HOURS, "u": claims.user_id})

        base = (mailer.conf("PORTAL_URL", "") or "").rstrip("/")
        verify_url = f"{base}/api/notify-groups/{key}/verify?token={token}"
        subject, text_body, html = mailer.group_verification(
            row["name"] or "Your college", GROUP_KEYS[key], verify_url)
        result = mailer.send_mail(email, subject, text_body, html)
        mailer.record(conn, claims, result)

        _audit(conn, claims, "college.group_verification_sent", "college",
               claims.college_id, {"group": key, "email": email,
                                   "status": result.status})

    if result.status == "skipped":
        raise HTTPException(503, result.error or "Email is not configured on this server")
    if result.status == "failed":
        raise HTTPException(502, result.error or "Could not send the confirmation email")
    return {"sent": True, "email": email, "valid_hours": VERIFICATION_VALID_HOURS}


@router.get("/notify-groups/{key}/verify")
def verify_group(key: str, token: str = Query(..., min_length=20, max_length=200)):
    """Opened from the confirmation email. Unauthenticated by necessity — the
    person clicking is a mailbox, not a logged-in user. The token is the proof:
    256 bits, single-use, and it expires.

    This cannot go through tenant_connection, because there is no logged-in
    user to derive a college from. It cannot go through a plain connection
    either: with no app.college_id set, app_college() is NULL, every RLS policy
    on group_verifications evaluates to NULL, and the UPDATE matches zero rows —
    so the link would fail as 'expired' every time. The work is therefore done
    inside consume_group_verification (migration 0010), a SECURITY DEFINER
    function that is narrow, token-gated, and the only path in.
    """
    if key not in GROUP_KEYS:
        raise HTTPException(404, "No such group")

    from ..db import engine
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT out_college_id, out_email "
                 "FROM consume_group_verification(:k, :t)"),
            {"k": key, "t": token}).mappings().first()

    if not row:
        # Deliberately one message for every failure — wrong token, used token,
        # expired token, address changed since. Distinguishing them would let
        # someone with a guessed token learn which guess was closer.
        raise HTTPException(410, "This confirmation link is no longer valid. "
                                 "Ask the placement office to send a new one.")

    return {"verified": True, "group": key, "email": row["out_email"],
            "message": "This address is confirmed. Announcements can now be sent to it."}
