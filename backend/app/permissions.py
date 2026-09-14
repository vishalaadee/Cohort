"""Role helpers for configurable CR access.

Two things this module guarantees:

  * A CR's capabilities are an explicit allow-list, resolved once per
    request rather than per check.
  * A set of capabilities is UNGRANTABLE to a CR — not "off by default",
    but impossible to represent in a grant. CRs turn over every academic
    year; the authority line must not drift with them.
"""
from __future__ import annotations

import json

from fastapi import HTTPException
from sqlalchemy import text

from .auth import Claims
from .db import tenant_connection

# --------------------------------------------------------------------------
# What a placement officer MAY delegate to a class representative.
# --------------------------------------------------------------------------
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
    {"key": "import_junior_roster", "label": "Import junior roster",
     "description": "Add non-final-year students for the assigned branch and issue their codes."},
    {"key": "export_registrations", "label": "Download registration sheets",
     "description": "Export the registration list for a drive, branch-scoped."},
]

CR_CAPABILITY_KEYS = {cap["key"] for cap in CR_CAPABILITIES}

# --------------------------------------------------------------------------
# What a placement officer may NEVER delegate.
#
# This is enforced structurally: the two sets are disjoint, normalisation
# filters against CR_CAPABILITY_KEYS, and test_permissions.py asserts the
# intersection stays empty. A UI bug or a hand-crafted API call cannot
# grant anything in this list.
# --------------------------------------------------------------------------
OFFICER_ONLY_CAPABILITIES = [
    {"key": "publish_drive", "label": "Publish a drive",
     "description": "Makes a drive visible to every student in the college."},
    {"key": "record_offer", "label": "Record offers and mark placed",
     "description": "Final outcomes are the placement officer's accountability."},
    {"key": "manage_policy", "label": "Change the placement policy",
     "description": "Changes eligibility and offer rules for everyone."},
    {"key": "manage_buckets", "label": "Change buckets",
     "description": "Defines what Tier 1, Dream and the rest mean."},
    {"key": "manage_cr_permissions", "label": "Change what CRs can do",
     "description": "A CR granting themselves authority is what the hierarchy prevents."},
    {"key": "export_full_roster", "label": "Export the full college roster",
     "description": "Whole-college personal data."},
    {"key": "export_resumes", "label": "Download resume bundles",
     "description": "Bulk personal data for a drive's registrants."},
    {"key": "manage_notifications", "label": "Change announcement addresses",
     "description": "Where student announcements are sent."},
    {"key": "manage_pro", "label": "Turn Pro features on",
     "description": "Commercial entitlements for the whole college."},
]

OFFICER_ONLY_KEYS = {cap["key"] for cap in OFFICER_ONLY_CAPABILITIES}

assert not (CR_CAPABILITY_KEYS & OFFICER_ONLY_KEYS), \
    "A capability cannot be both CR-grantable and officer-only"

# CR memberships created before migration 0007 have permissions = NULL.
# Keep the previous safe pilot surface until an admin saves an explicit list.
# TODO(2027-07): once every CR membership has an explicit array, change the
# None case to return [] so "no grants" means "no access".
LEGACY_CR_CAPABILITIES = {
    "view_branch_dashboard",
    "view_branch_roster",
    "manage_branch_pipeline",
    "manage_branch_questions",
}


def normalize_cr_permissions(raw) -> list[str]:
    """Filter a stored grant list down to what is actually grantable.

    Anything unknown, or officer-only, is dropped rather than honoured.
    """
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


def get_cr_permissions(claims: Claims, conn=None) -> list[str]:
    """Resolve a CR's grants.

    Pass an open connection when you already have one — otherwise this opens
    its own transaction, and a handler that checks two capabilities would
    pay for two round trips.
    """
    if claims.role != "sub_admin":
        return []
    if not claims.user_id or not claims.college_id:
        return []

    sql = text("""
        SELECT permissions
        FROM memberships
        WHERE user_id = :uid AND college_id = :cid
          AND role = 'sub_admin' AND status = 'active'
        LIMIT 1
    """)
    params = {"uid": claims.user_id, "cid": claims.college_id}

    if conn is not None:
        return normalize_cr_permissions(conn.execute(sql, params).scalar())
    with tenant_connection(claims) as own:
        return normalize_cr_permissions(own.execute(sql, params).scalar())


def require_cr_capability(claims: Claims, capability: str, conn=None) -> None:
    """Gate a handler on one capability.

    Officers and owners pass everything. A CR passes only what has been
    explicitly granted, and can never pass an officer-only capability —
    those are not in CR_CAPABILITY_KEYS, so normalisation drops them even
    if one somehow appears in the stored array.
    """
    require_staff(claims)
    if claims.role in ("owner", "admin"):
        return
    if capability in OFFICER_ONLY_KEYS:
        raise HTTPException(403, "Only the placement officer can do that")
    if capability not in CR_CAPABILITY_KEYS:
        raise HTTPException(500, "Unknown CR permission")
    if capability not in get_cr_permissions(claims, conn):
        raise HTTPException(403, "Your CR account has not been granted this access")
