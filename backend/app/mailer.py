"""Outbound mail.

Until now nothing in Cohort sent email. `publish_drive` wrote a row to
`notification_log` and returned; that row recorded the *decision* to announce,
and nothing consumed it. This module is what makes the decision real.

Three things it is deliberately not:

  * Not a queue. Cohort announces to a college's group address — one message
    per publish, not one per student — so a synchronous send with a short
    timeout costs the officer a second and tells them honestly whether it
    worked. A queue becomes right when we send per-student; see
    docs/GTM_ROLLOUT.md for when that is.
  * Not a From-header rewriter. The message is sent as the college's own
    configured address, with the student or officer in Reply-To if relevant.
    Authenticating as one address and putting someone else's in From is how a
    sending domain's reputation gets destroyed by SPF and DMARC failures.
  * Not a place that raises. A send failure is reported, logged and returned —
    it never turns a successful publish into a 500, because the drive really
    was published and telling the officer otherwise would be a lie.

Configuration, all optional — with none of it set, sends are skipped cleanly
and the caller is told why:

    SMTP_HOST          smtp.gmail.com | email-smtp.ap-south-1.amazonaws.com
    SMTP_PORT          587
    SMTP_USER          the SMTP username (SES: the IAM SMTP credential)
    SMTP_PASSWORD      the SMTP password / app password
    SMTP_FROM          placements@yourcollege.ac.in
    SMTP_FROM_NAME     Placement Cell
    SMTP_STARTTLS      true (default) | false
    SMTP_TIMEOUT       15 (seconds)
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from .config import settings

logger = logging.getLogger("cohort.mail")

# A single message carrying the JD plus a couple of extras. Gmail rejects
# above 25 MB and most college mail relays are stricter; refusing at 10 MB
# gives a clear error instead of a silent bounce hours later.
MAX_TOTAL_ATTACHMENT_BYTES = 10 * 1024 * 1024


def conf(name: str, default=None):
    """Read config without requiring the field to be declared on Settings.

    main.py already reads `allowed_origins` this way. Matching it means
    deploying this module does not require editing config.py first.
    """
    value = getattr(settings, name.lower(), None)
    if value in (None, ""):
        import os
        value = os.getenv(name.upper()) or os.getenv(name.lower())
    return default if value in (None, "") else value


def is_configured() -> bool:
    return bool(conf("SMTP_HOST") and conf("SMTP_FROM"))


@dataclass
class Attachment:
    filename: str
    mime: str
    data: bytes

    @property
    def size(self) -> int:
        return len(self.data)


@dataclass
class SendResult:
    """What actually happened. `status` mirrors mail_log.status."""
    status: str                      # 'sent' | 'failed' | 'skipped'
    to: str = ""
    subject: str = ""
    attachments: int = 0
    error: str | None = None
    detail: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == "sent"


def _split_mime(mime: str) -> tuple[str, str]:
    main, _, sub = (mime or "application/octet-stream").partition("/")
    return (main or "application"), (sub or "octet-stream")


def send_mail(to: str,
              subject: str,
              text_body: str,
              html_body: str | None = None,
              attachments: list[Attachment] | None = None,
              reply_to: str | None = None) -> SendResult:
    """Send one message. Returns a SendResult; never raises for a send failure."""
    attachments = attachments or []
    result = SendResult(status="skipped", to=to, subject=subject,
                        attachments=len(attachments))

    if not to:
        result.error = "No recipient address"
        return result

    if not is_configured():
        result.error = ("Email is not configured on this server "
                        "(SMTP_HOST / SMTP_FROM are unset)")
        return result

    total = sum(a.size for a in attachments)
    if total > MAX_TOTAL_ATTACHMENT_BYTES:
        result.status = "failed"
        result.error = (f"Attachments total {total // 1024 // 1024} MB, over the "
                        f"{MAX_TOTAL_ATTACHMENT_BYTES // 1024 // 1024} MB limit")
        return result

    from_addr = str(conf("SMTP_FROM"))
    from_name = str(conf("SMTP_FROM_NAME", "Placement Cell"))

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((from_name, from_addr))
    msg["To"] = to
    msg["Message-ID"] = make_msgid()
    if reply_to:
        # The human who should get the reply — never the From address, so
        # SPF/DMARC still pass for the sending domain.
        msg["Reply-To"] = reply_to
    # Announcements go to a group address; replies to a list shouldn't
    # generate auto-responders back at us.
    msg["Auto-Submitted"] = "auto-generated"

    msg.set_content(text_body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")

    for a in attachments:
        main, sub = _split_mime(a.mime)
        msg.add_attachment(a.data, maintype=main, subtype=sub,
                           filename=a.filename)

    host = str(conf("SMTP_HOST"))
    port = int(conf("SMTP_PORT", 587))
    user = conf("SMTP_USER")
    password = conf("SMTP_PASSWORD")
    timeout = int(conf("SMTP_TIMEOUT", 15))
    starttls = str(conf("SMTP_STARTTLS", "true")).lower() not in ("false", "0", "no")

    try:
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=timeout,
                                      context=ssl.create_default_context())
        else:
            server = smtplib.SMTP(host, port, timeout=timeout)
        with server:
            server.ehlo()
            if starttls and port != 465:
                server.starttls(context=ssl.create_default_context())
                server.ehlo()
            if user and password:
                server.login(str(user), str(password))
            server.send_message(msg)

        result.status = "sent"
        logger.info("mail sent to=%s subject=%r attachments=%d",
                    to, subject, len(attachments))
        return result

    except smtplib.SMTPAuthenticationError:
        # Deliberately not echoing the server's message: it can contain the
        # username, and on Gmail it contains a URL with the account in it.
        result.status = "failed"
        result.error = "SMTP rejected the credentials. Check SMTP_USER / SMTP_PASSWORD."
    except smtplib.SMTPRecipientsRefused:
        result.status = "failed"
        result.error = f"The mail server refused the address {to}."
    except (smtplib.SMTPException, OSError) as exc:
        result.status = "failed"
        result.error = f"{type(exc).__name__}: {exc}"

    logger.error("mail failed to=%s subject=%r error=%s", to, subject, result.error)
    return result


def record(conn, claims, result: SendResult, notification_id: int | None = None) -> None:
    """Write the send to mail_log. Append-only, never raises into the caller."""
    from sqlalchemy import text
    try:
        conn.execute(text("""
            INSERT INTO mail_log (college_id, notification_id, to_address,
                                  subject, status, error, attachments)
            VALUES (:c, :n, :t, :s, :st, :e, :a)
        """), {"c": claims.college_id, "n": notification_id, "t": result.to,
               "s": result.subject, "st": result.status,
               "e": result.error, "a": result.attachments})
    except Exception:
        logger.exception("could not write mail_log row")


# ---------------------------------------------------------------------------
# Templates
#
# Plain text is built alongside the HTML rather than after it, because a
# college mail relay that strips HTML is common and a student reading the
# text/plain part should still get the dates and the link.
# ---------------------------------------------------------------------------
def _esc(value) -> str:
    from html import escape
    return escape("" if value is None else str(value))


def drive_announcement(drive: dict, college_name: str, portal_url: str,
                       attachments: list[Attachment]) -> tuple[str, str, str]:
    """Returns (subject, text_body, html_body) for a newly published drive."""
    name = drive.get("name") or "A new drive"
    role = drive.get("role_title")
    # ASCII hyphen, not an em dash. A non-ASCII character in a Subject forces
    # RFC 2047 encoded-words for that run only, and the resulting mixed header
    # renders literally as =?utf-8?b?...?= on the older Zimbra and Roundcube
    # installs a lot of colleges still run. The body is free to use real
    # punctuation; it is a MIME part with its own charset.
    subject = f"{name} - registrations open" + (f" ({role})" if role else "")

    rows: list[tuple[str, str]] = []
    if role:
        rows.append(("Role", str(role)))
    if drive.get("package") is not None:
        rows.append(("Package", f"{drive['package']} LPA"))
    if drive.get("bucket_label"):
        rows.append(("Category", str(drive["bucket_label"])))
    if drive.get("deadline"):
        rows.append(("Register by", str(drive["deadline"])))
    if drive.get("test_date"):
        rows.append(("Test / visit", str(drive["test_date"])))
    if drive.get("venue"):
        rows.append(("Venue", str(drive["venue"])))
    if drive.get("restriction_note"):
        rows.append(("Please note", str(drive["restriction_note"])))

    text_lines = [f"{name} — registrations are open.", ""]
    text_lines += [f"{k}: {v}" for k, v in rows]
    if attachments:
        text_lines += ["", "Attached: " + ", ".join(a.filename for a in attachments)]
    text_lines += [
        "",
        f"Check whether you are eligible and register here: {portal_url}",
        "",
        "Eligibility is shown on the portal with the reason, so if you cannot",
        "register it will tell you why.",
        "",
        f"{college_name} — Placement Cell",
        "This is an automated message from the placement portal.",
    ]

    row_html = "".join(
        f'<tr><td style="padding:4px 12px 4px 0;color:#6b6b6b;white-space:nowrap">{_esc(k)}</td>'
        f'<td style="padding:4px 0;font-weight:600">{_esc(v)}</td></tr>'
        for k, v in rows)

    attach_html = ""
    if attachments:
        names = ", ".join(_esc(a.filename) for a in attachments)
        attach_html = (f'<p style="margin:16px 0 0;color:#6b6b6b;font-size:13px">'
                       f'Attached: {names}</p>')

    html = f"""<!doctype html>
<html><body style="margin:0;padding:24px;background:#f6f6f4;
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;color:#1a1a1a">
  <div style="max-width:520px;margin:0 auto;background:#fff;border-radius:10px;
              padding:28px;border:1px solid #e6e6e2">
    <p style="margin:0 0 4px;font-size:13px;color:#6b6b6b">{_esc(college_name)} · Placement Cell</p>
    <h1 style="margin:0 0 18px;font-size:21px;line-height:1.3">{_esc(name)}</h1>
    <p style="margin:0 0 18px">Registrations are open.</p>
    <table style="border-collapse:collapse;font-size:14px">{row_html}</table>
    {attach_html}
    <p style="margin:26px 0 0">
      <a href="{_esc(portal_url)}" style="display:inline-block;padding:11px 22px;
         background:#7b1e3a;color:#fff;text-decoration:none;border-radius:6px;
         font-weight:600;font-size:14px">Check eligibility and register</a>
    </p>
    <p style="margin:22px 0 0;font-size:13px;color:#6b6b6b">
      The portal shows whether you are eligible and, if not, the reason.
    </p>
  </div>
  <p style="max-width:520px;margin:14px auto 0;font-size:12px;color:#8a8a8a;text-align:center">
    Automated message from the placement portal. Please do not reply.
  </p>
</body></html>"""

    return subject, "\n".join(text_lines), html


def group_verification(college_name: str, group_label: str,
                       verify_url: str) -> tuple[str, str, str]:
    """Sent to a group address to prove the placement cell controls it."""
    subject = f"Confirm this address for {college_name} placement announcements"
    text_body = (
        f"{college_name} has set this address as its {group_label} announcement "
        f"address on the placement portal.\n\n"
        f"Until someone who receives mail here confirms it, no announcement will "
        f"be sent to it.\n\n"
        f"Confirm: {verify_url}\n\n"
        f"The link is valid for 48 hours. If you were not expecting this, ignore "
        f"it — nothing will be sent to this address.\n"
    )
    html = f"""<!doctype html>
<html><body style="margin:0;padding:24px;background:#f6f6f4;
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;color:#1a1a1a">
  <div style="max-width:520px;margin:0 auto;background:#fff;border-radius:10px;
              padding:28px;border:1px solid #e6e6e2">
    <h1 style="margin:0 0 16px;font-size:19px">Confirm this address</h1>
    <p style="margin:0 0 14px">{_esc(college_name)} has set this address as its
      <b>{_esc(group_label)}</b> announcement address on the placement portal.</p>
    <p style="margin:0 0 20px">No announcement will be sent here until someone
      who receives mail at this address confirms it.</p>
    <p style="margin:0 0 20px">
      <a href="{_esc(verify_url)}" style="display:inline-block;padding:11px 22px;
         background:#7b1e3a;color:#fff;text-decoration:none;border-radius:6px;
         font-weight:600;font-size:14px">Confirm this address</a>
    </p>
    <p style="margin:0;font-size:13px;color:#6b6b6b">Valid for 48 hours. If you
      were not expecting this, ignore it — nothing will be sent here.</p>
  </div>
</body></html>"""
    return subject, text_body, html
