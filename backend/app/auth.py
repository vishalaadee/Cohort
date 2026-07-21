from dataclasses import dataclass

import jwt
from fastapi import Header

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
    # DEV ONLY: lets you test any scope from the browser/curl without a login.
    x_demo_role: str | None = Header(default=None),
    x_demo_college: str | None = Header(default=None),
    x_demo_branch: str | None = Header(default=None),
    x_demo_user: str | None = Header(default=None),
) -> Claims:
    """Real path: verify the Bearer JWT and read scope claims from it.
    Dev path: no/invalid token -> fall back to a scope (default admin @ the
    demo college) so the POC renders. Replace the dev path with a hard 401
    the moment real login is wired up."""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1]
        try:
            payload = jwt.decode(
                token, settings.jwt_secret, algorithms=[settings.jwt_alg]
            )
            return Claims(
                role=payload.get("role", "student"),
                college_id=_int_or_none(payload.get("college_id")),
                branch_id=_int_or_none(payload.get("branch_id")),
                user_id=_int_or_none(payload.get("user_id")),
            )
        except jwt.PyJWTError:
            pass  # fall through to dev fallback

    if settings.dev_fallback:
        return Claims(
            role=x_demo_role or "admin",
            college_id=_int_or_none(x_demo_college) or 1,
            branch_id=_int_or_none(x_demo_branch),
            user_id=_int_or_none(x_demo_user),
        )

    # Once dev_fallback is off, unauthenticated requests get an empty scope,
    # and RLS then returns zero rows for everything.
    return Claims(role="", college_id=None)
