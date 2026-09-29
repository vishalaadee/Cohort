from dataclasses import dataclass

import jwt
from fastapi import Header, HTTPException

from .config import settings


@dataclass
class Claims:
    role: str
    college_id: int | None = None
    branch_id: int | None = None
    user_id: int | None = None


def _int_or_none(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def get_claims(
    authorization: str | None = Header(default=None),
) -> Claims:
    """Verify the Bearer JWT and read scope claims from it.

    The X-Demo-* header fallback that used to live here has been REMOVED.

    What it did: when DEV_FALLBACK was true, an unauthenticated request
    carrying `X-Demo-Role: owner` and `X-Demo-College: <n>` was handed owner
    claims. Every RLS policy in this schema is shaped
    `app_role() = 'owner' OR college_id = app_college()`, so those headers
    granted unrestricted read and write across every college in the database
    with no token at all. The flag defaulted to False, but it was passed
    through docker-compose as `DEV_FALLBACK: ${DEV_FALLBACK}` — one character
    in .env away from live, with no log line to say so.

    Real login now exists (Google SSO, password, and activation-code claim),
    which is the condition the original docstring set for deleting this path.
    Use a real token in development; scripts/dev-token.py mints one.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Sign in to continue.")

    token = authorization.split(" ", 1)[1]
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_alg]
        )
    except jwt.PyJWTError:
        raise HTTPException(401, "Your session is invalid or has expired. Please sign in again.")

    role = payload.get("role", "student")
    # A token is not permitted to assert a role the application does not know.
    # Without this, a forged or malformed 'role' string flows into
    # set_config('app.role', ...) and is compared inside every RLS policy.
    if role not in ("owner", "admin", "sub_admin", "student", "alumni"):
        raise HTTPException(401, "Your session is invalid or has expired. Please sign in again.")

    return Claims(
        role=role,
        college_id=_int_or_none(payload.get("college_id")),
        branch_id=_int_or_none(payload.get("branch_id")),
        user_id=_int_or_none(payload.get("user_id")),
    )
