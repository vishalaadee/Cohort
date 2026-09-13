"""Role helpers for configurable CR access."""
from __future__ import annotations

import json

from fastapi import HTTPException
from sqlalchemy import text

from .auth import Claims
from .db import tenant_connection

CR_CAPABILITIES = [
    {"key": "view_branch_dashboard", "label": "View branch dashboard",
     "description": "See branch-scoped placement counts and funnel."},
    {"key": "view_branch_roster", "label": "View branch roster",
     "description": "See students and login status for the assigned branch."},
    {"key": "manage_branch_pipeline", "label": "Update branch pipeline rounds",
     "description": "See drive registrations and update interview rounds, not final statuses."},
    {"key": "manage_branch_questions", "label": "Escalate branch questions",
     "description": "See branch questions and escalate open items to placement officers."},
    {"key": "view_activation_codes", "label": "Export activation codes",
     "description": "Download unclaimed activation codes for the assigned branch."},
]

CR_CAPABILITY_KEYS = {cap["key"] for cap in CR_CAPABILITIES}

# Existing CR memberships created before this migration have permissions=NULL.
# Keep the previous safe pilot surface until an admin saves an explicit list.
LEGACY_CR_CAPABILITIES = {
    "view_branch_dashboard",
    "view_branch_roster",
    "manage_branch_pipeline",
    "manage_branch_questions",
}


def normalize_cr_permissions(raw) -> list[str]:
    if raw is None:
        return sorted(LEGACY_CR_CAPABILITIES)
    if isinstance(raw, str):
        raw = json.loads(raw)
    if not isinstance(raw, list):
        return []
    return sorted({item for item in raw if item in CR_CAPABILITY_KEYS})


def require_staff(claims: Claims) -> None:
    if claims.role not in ("owner", "admin", "sub_admin"):
        raise HTTPException(403, "Placement-cell access required")
    if claims.role != "owner" and not claims.college_id:
        raise HTTPException(403, "No college scope on this account")


def require_placement_officer(claims: Claims) -> None:
    require_staff(claims)
    if claims.role == "sub_admin":
        raise HTTPException(403, "Only the placement officer can do that")


def get_cr_permissions(claims: Claims) -> list[str]:
    if claims.role != "sub_admin":
        return []
    if not claims.user_id or not claims.college_id:
        return []
    with tenant_connection(claims) as conn:
        raw = conn.execute(text("""
            SELECT permissions
            FROM memberships
            WHERE user_id=:uid AND college_id=:cid
              AND role='sub_admin' AND status='active'
            LIMIT 1
        """), {"uid": claims.user_id, "cid": claims.college_id}).scalar()
    return normalize_cr_permissions(raw)


def require_cr_capability(claims: Claims, capability: str) -> None:
    require_staff(claims)
    if claims.role in ("owner", "admin"):
        return
    if capability not in CR_CAPABILITY_KEYS:
        raise HTTPException(500, "Unknown CR permission")
    if capability not in get_cr_permissions(claims):
        raise HTTPException(403, "Your CR account has not been granted this access")
