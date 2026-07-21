"""Configurable eligibility: a safe rule evaluator + placement-policy engine.

Design contract:
  * Rules are DATA (a JSON condition tree), never code. This module is the
    only interpreter, with a whitelist of operators, a depth limit, and a
    condition-count limit — so a malicious or malformed rule can't execute
    anything or blow up the server.
  * Every failure returns a human reason, because "why am I not eligible" is
    the #1 question students ask placement cells.

Rule tree shape (any nesting of):
  {"all": [<node>, ...]}   every child must pass
  {"any": [<node>, ...]}   at least one child must pass
  {"not": <node>}          child must fail
  {"field": "cgpa", "op": ">=", "value": 7.0, "label": "CGPA"}   leaf
"""

MAX_DEPTH = 5
MAX_CONDITIONS = 50

_OPS = {
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    ">":  lambda a, b: a > b,
    "<":  lambda a, b: a < b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    "in":     lambda a, b: a in b,
    "not_in": lambda a, b: a not in b,
    "between": lambda a, b: b[0] <= a <= b[1],
}

_OP_TEXT = {">=": "at least", "<=": "at most", ">": "more than", "<": "less than",
            "==": "exactly", "!=": "not", "in": "one of", "not_in": "not one of",
            "between": "between"}


class RuleError(ValueError):
    """Raised for malformed rule trees (admin-facing validation error)."""


def evaluate_rules(rules: dict | None, student: dict) -> tuple[bool, list[str]]:
    """Evaluate a rule tree against a flat student attribute dict.
    Returns (eligible, reasons_for_failure). Empty/None rules => eligible."""
    if not rules:
        return True, []
    count = _count_conditions(rules, 0)
    if count > MAX_CONDITIONS:
        raise RuleError(f"Rule has {count} conditions; max is {MAX_CONDITIONS}")
    ok, reasons = _eval(rules, student, depth=0)
    return ok, reasons


def _count_conditions(node, n):
    if not isinstance(node, dict):
        raise RuleError("Rule nodes must be objects")
    if "field" in node:
        return n + 1
    for key in ("all", "any"):
        if key in node:
            return sum(_count_conditions(c, 0) for c in node[key]) + n
    if "not" in node:
        return _count_conditions(node["not"], n)
    raise RuleError(f"Unknown rule node: {list(node.keys())}")


def _eval(node: dict, student: dict, depth: int) -> tuple[bool, list[str]]:
    if depth > MAX_DEPTH:
        raise RuleError(f"Rule nesting exceeds depth {MAX_DEPTH}")

    if "field" in node:
        return _eval_leaf(node, student)

    if "all" in node:
        reasons: list[str] = []
        ok = True
        for child in node["all"]:
            c_ok, c_reasons = _eval(child, student, depth + 1)
            if not c_ok:
                ok = False
                reasons.extend(c_reasons)
        return ok, reasons

    if "any" in node:
        collected: list[str] = []
        for child in node["any"]:
            c_ok, c_reasons = _eval(child, student, depth + 1)
            if c_ok:
                return True, []
            collected.extend(c_reasons)
        return False, [f"none of the alternatives matched ({'; '.join(collected)})"]

    if "not" in node:
        c_ok, _ = _eval(node["not"], student, depth + 1)
        return (not c_ok), ([] if not c_ok else ["an exclusion rule matched"])

    raise RuleError(f"Unknown rule node: {list(node.keys())}")


def _eval_leaf(node: dict, student: dict) -> tuple[bool, list[str]]:
    field = node.get("field")
    op = node.get("op")
    expected = node.get("value")
    label = node.get("label", field)

    if op not in _OPS:
        raise RuleError(f"Operator '{op}' is not allowed")
    if field not in student or student[field] is None:
        return False, [f"{label} is not on record — ask your placement cell to update your profile"]

    actual = student[field]
    try:
        ok = _OPS[op](actual, expected)
    except TypeError:
        return False, [f"{label} has an unexpected format"]
    if ok:
        return True, []
    shown = ", ".join(map(str, expected)) if isinstance(expected, (list, tuple)) else expected
    return False, [f"{label} is {actual}; needs to be {_OP_TEXT[op]} {shown}"]


# --------------------------------------------------------------------------
# Layer 3: college-wide placement policy (parameterized templates)
# --------------------------------------------------------------------------

def check_policy(policy: dict | None, offers: list[dict], target_package: float | None
                 ) -> tuple[bool, str | None]:
    """Can this student (with these existing offers) sit for a drive paying
    target_package? offers = [{"package": 600000}, ...]. Returns (allowed, reason).

    Templates (all optional keys in the college's placement_policy JSON):
      one_offer      bool  — placed once => done, no further drives
      max_offers     int   — hard cap on offers
      slabs          list  — [{"name","max_lpa"?}] ascending; last slab open-ended
      upgrade        str   — "higher_slab" | "multiplier" | "both" | "none"
      multiplier     float — target must be >= multiplier * best current offer
    """
    policy = policy or {}
    if not offers:
        return True, None

    if policy.get("one_offer"):
        return False, "College policy: one offer per student — you are already placed"

    max_offers = policy.get("max_offers")
    if max_offers and len(offers) >= max_offers:
        return False, f"College policy: maximum {max_offers} offers reached"

    best = max(o["package"] or 0 for o in offers)
    upgrade = policy.get("upgrade", "none")
    if upgrade == "none" or target_package is None:
        return True, None

    def slab_index(amount_lpa: float, slabs: list) -> int:
        for i, s in enumerate(slabs):
            cap = s.get("max_lpa")
            if cap is None or amount_lpa <= cap:
                return i
        return len(slabs) - 1

    if upgrade in ("higher_slab", "both"):
        slabs = policy.get("slabs") or []
        if slabs:
            cur = slab_index(best / 100000, slabs)
            tgt = slab_index(target_package / 100000, slabs)
            if tgt <= cur:
                return False, (f"College policy: you are placed in slab "
                               f"'{slabs[cur]['name']}' — you may only sit for drives in a higher slab")

    if upgrade in ("multiplier", "both"):
        mult = float(policy.get("multiplier") or 1.0)
        if target_package < mult * best:
            return False, (f"College policy: drives must pay at least {mult}x your current "
                           f"best offer (₹{mult * best / 100000:.1f} LPA)")

    return True, None


def legacy_rules_from_columns(company: dict) -> dict:
    """Bridge: build a rule tree from the old three columns so drives created
    before this feature keep working identically."""
    conds = []
    if company.get("min_cgpa") not in (None, 0):
        conds.append({"field": "cgpa", "op": ">=", "value": float(company["min_cgpa"]), "label": "CGPA"})
    if company.get("max_backlogs") is not None:
        conds.append({"field": "backlogs", "op": "<=", "value": int(company["max_backlogs"]), "label": "Backlogs"})
    if company.get("eligible_branches"):
        conds.append({"field": "branch", "op": "in", "value": list(company["eligible_branches"]), "label": "Branch"})
    return {"all": conds} if conds else {}
