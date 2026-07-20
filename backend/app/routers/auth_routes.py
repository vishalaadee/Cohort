"""Authentication & onboarding.

Two front doors, one outcome (a scoped JWT):

  1. Google SSO   — frontend gets an ID token from Google's button, posts it
                    here; we verify it against Google's certs, then match the
                    email to a membership (admins) or roster row (students).
                    First student sign-in auto-creates + links their account.
  2. Password     — email+password login for admins and for students at
                    colleges without Google accounts. Those students first
                    "claim" their account with an activation code from the
                    CSV import, choosing a password in the process.

These endpoints are the ONLY place allowed to open a DB connection with the
'owner' system scope — identity has to be resolved before a tenant scope
exists. Everything they read/write here is the minimum needed for that.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import text

from ..auth import Claims, get_claims
from ..config import settings
from ..db import tenant_connection
from ..security import create_token, hash_password, login_limiter, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

SYSTEM = Claims(role="owner")  # internal system scope for identity resolution


# ---------------------------------------------------------------- google sso
def _real_google_verify(credential: str) -> dict:
    """Verify a Google ID token. Split out so tests can substitute a fake."""
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token

    info = id_token.verify_oauth2_token(
        credential, google_requests.Request(), audience=settings.google_client_id
    )
    return info


google_verify = _real_google_verify  # tests may monkeypatch this


class GoogleIn(BaseModel):
    credential: str


@router.post("/google")
def login_with_google(body: GoogleIn):
    if not settings.google_client_id:
        raise HTTPException(503, "Google sign-in is not configured on this server")
    try:
        info = google_verify(body.credential)
    except Exception:
        raise HTTPException(401, "Google token could not be verified")
    if not info.get("email_verified"):
        raise HTTPException(401, "Google account email is not verified")

    email = info["email"].lower()
    sub = info.get("sub")
    name = info.get("name")

    with tenant_connection(SYSTEM) as conn:
        # admins / sub-admins / owner first: membership joined to user email
        m = conn.execute(text("""
            SELECT u.id AS user_id, m.role, m.college_id, m.branch_id
            FROM memberships m JOIN users u ON u.id = m.user_id
            WHERE lower(u.email) = :email AND m.status = 'active'
            ORDER BY CASE m.role WHEN 'owner' THEN 0 WHEN 'admin' THEN 1
                                 WHEN 'sub_admin' THEN 2 ELSE 3 END
            LIMIT 1
        """), {"email": email}).mappings().first()
        if m:
            conn.execute(text(
                "UPDATE users SET external_auth_id = COALESCE(external_auth_id, :sub) WHERE id = :uid"
            ), {"sub": sub, "uid": m["user_id"]})
            return _token_response(conn, m["user_id"], m["role"], m["college_id"], m["branch_id"])

        # students: match roster email
        rows = conn.execute(text("""
            SELECT id, college_id, branch_id, user_id, full_name
            FROM students WHERE lower(email) = :email
        """), {"email": email}).mappings().all()
        if not rows:
            raise HTTPException(403, "No roster entry or membership matches this Google account. Ask your placement cell to add you, or use Claim account.")
        if len(rows) > 1:
            raise HTTPException(409, "This email appears in more than one college roster. Use Claim account with your roll number instead.")
        st = rows[0]

        if st["user_id"]:
            uid = st["user_id"]
            conn.execute(text(
                "UPDATE users SET external_auth_id = COALESCE(external_auth_id, :sub) WHERE id = :uid"
            ), {"sub": sub, "uid": uid})
        else:
            # first sign-in: auto-create + link + verify (Google verified the email)
            uid = conn.execute(text("""
                INSERT INTO users (email, full_name, external_auth_id)
                VALUES (:email, :name, :sub) RETURNING id
            """), {"email": email, "name": name or st["full_name"], "sub": sub}).scalar_one()
            conn.execute(text("""
                UPDATE students SET user_id = :uid, verified = true, claimed_at = now(),
                       activation_code = NULL
                WHERE id = :sid
            """), {"uid": uid, "sid": st["id"]})

        return _token_response(conn, uid, "student", st["college_id"], st["branch_id"])


# ------------------------------------------------------------ password login
class LoginIn(BaseModel):
    email: EmailStr
    password: str


@router.post("/login")
def login_with_password(body: LoginIn, request: Request):
    key = f"login:{(request.client.host if request.client else '?')}:{body.email.lower()}"
    if not login_limiter.allow(key):
        raise HTTPException(429, "Too many attempts. Try again in a few minutes.")

    with tenant_connection(SYSTEM) as conn:
        u = conn.execute(text(
            "SELECT id, password_hash FROM users WHERE lower(email) = :e"
        ), {"e": body.email.lower()}).mappings().first()
        if not u or not verify_password(body.password, u["password_hash"]):
            raise HTTPException(401, "Email or password is incorrect")

        # role resolution: membership first, else linked student
        m = conn.execute(text("""
            SELECT role, college_id, branch_id FROM memberships
            WHERE user_id = :uid AND status = 'active'
            ORDER BY CASE role WHEN 'owner' THEN 0 WHEN 'admin' THEN 1
                               WHEN 'sub_admin' THEN 2 ELSE 3 END LIMIT 1
        """), {"uid": u["id"]}).mappings().first()
        if m:
            return _token_response(conn, u["id"], m["role"], m["college_id"], m["branch_id"])

        st = conn.execute(text(
            "SELECT college_id, branch_id FROM students WHERE user_id = :uid LIMIT 1"
        ), {"uid": u["id"]}).mappings().first()
        if st:
            return _token_response(conn, u["id"], "student", st["college_id"], st["branch_id"])

    raise HTTPException(403, "Account exists but has no role. Contact your placement cell.")


# ------------------------------------------------------------- claim account
class ClaimIn(BaseModel):
    college_slug: str
    roll_no: str
    activation_code: str
    password: str = Field(min_length=8, max_length=128)


@router.post("/claim")
def claim_account(body: ClaimIn, request: Request):
    """For colleges without Google accounts: a student turns their roster row
    into a login using the activation code their placement cell gave them."""
    key = f"claim:{(request.client.host if request.client else '?')}"
    if not login_limiter.allow(key):
        raise HTTPException(429, "Too many attempts. Try again in a few minutes.")

    with tenant_connection(SYSTEM) as conn:
        st = conn.execute(text("""
            SELECT s.id, s.college_id, s.branch_id, s.email, s.full_name,
                   s.user_id, s.activation_code
            FROM students s JOIN colleges c ON c.id = s.college_id
            WHERE c.slug = :slug AND upper(s.roll_no) = upper(:roll)
        """), {"slug": body.college_slug.lower(), "roll": body.roll_no}).mappings().first()

        if not st or not st["activation_code"] \
           or st["activation_code"].upper() != body.activation_code.upper():
            # one message for all failure shapes — don't leak which part matched
            raise HTTPException(403, "Details don't match. Check your college code, roll number and activation code.")
        if st["user_id"]:
            raise HTTPException(409, "This account is already claimed. Use Sign in instead.")

        existing = conn.execute(text(
            "SELECT id FROM users WHERE lower(email) = :e"
        ), {"e": st["email"].lower()}).scalar()
        if existing:
            raise HTTPException(409, "A login already exists for this email. Use Sign in.")

        uid = conn.execute(text("""
            INSERT INTO users (email, full_name, password_hash)
            VALUES (:email, :name, :ph) RETURNING id
        """), {"email": st["email"].lower(), "name": st["full_name"],
               "ph": hash_password(body.password)}).scalar_one()
        conn.execute(text("""
            UPDATE students SET user_id = :uid, verified = true,
                   claimed_at = now(), activation_code = NULL
            WHERE id = :sid
        """), {"uid": uid, "sid": st["id"]})

        return _token_response(conn, uid, "student", st["college_id"], st["branch_id"])


# --------------------------------------------------------------------- misc
@router.get("/config")
def auth_config():
    """Frontend bootstrap: which sign-in methods to render."""
    return {"google_client_id": settings.google_client_id,
            "dev_fallback": settings.dev_fallback}


@router.get("/me")
def me(claims: Claims = Depends(get_claims)):
    if not claims.user_id and not settings.dev_fallback:
        raise HTTPException(401, "Not signed in")
    with tenant_connection(SYSTEM) as conn:
        u = None
        if claims.user_id:
            u = conn.execute(text(
                "SELECT id, email, full_name FROM users WHERE id = :uid"
            ), {"uid": claims.user_id}).mappings().first()
        college = None
        if claims.college_id:
            college = conn.execute(text(
                "SELECT id, name, slug FROM colleges WHERE id = :cid"
            ), {"cid": claims.college_id}).mappings().first()
    return {"user": dict(u) if u else None,
            "role": claims.role, "college": dict(college) if college else None,
            "branch_id": claims.branch_id}


def _token_response(conn, user_id: int, role: str,
                    college_id: int | None, branch_id: int | None):
    u = conn.execute(text(
        "SELECT email, full_name FROM users WHERE id = :uid"
    ), {"uid": user_id}).mappings().one()
    token = create_token(user_id=user_id, role=role,
                         college_id=college_id, branch_id=branch_id)
    return {"token": token, "role": role, "college_id": college_id,
            "branch_id": branch_id,
            "user": {"id": user_id, "email": u["email"], "full_name": u["full_name"]}}
