# Run from backend/: PYTHONPATH=. python3 tests/test_eligibility.py
from app.eligibility import evaluate_rules, check_policy, legacy_rules_from_columns, RuleError

S = {"cgpa": 8.42, "backlogs": 0, "branch": "CSE", "tenth_pct": 88.0, "gap_years": 0}

# 1. simple pass
ok, r = evaluate_rules({"all":[{"field":"cgpa","op":">=","value":7}]}, S)
assert ok and not r
# 2. simple fail with readable reason
ok, r = evaluate_rules({"all":[{"field":"cgpa","op":">=","value":9,"label":"CGPA"}]}, S)
assert not ok and "CGPA is 8.42" in r[0]
# 3. nested any: fails one branch, passes other
rules = {"all":[
  {"field":"branch","op":"in","value":["CSE","ISE"],"label":"Branch"},
  {"any":[{"field":"backlogs","op":"<=","value":0},{"field":"cgpa","op":">=","value":9.5}]}]}
ok, _ = evaluate_rules(rules, S); assert ok
# 4. missing attribute => fail with guidance, not crash
ok, r = evaluate_rules({"all":[{"field":"twelfth_pct","op":">=","value":80,"label":"12th %"}]}, S)
assert not ok and "not on record" in r[0]
# 5. 'not' exclusion
ok, _ = evaluate_rules({"not":{"field":"gap_years","op":">","value":1}}, S); assert ok
# 6. unknown operator rejected (no code execution paths)
try:
    evaluate_rules({"all":[{"field":"cgpa","op":"__import__","value":0}]}, S); assert False
except RuleError: pass
# 7. depth bomb rejected
deep = {"field":"cgpa","op":">=","value":1}
for _ in range(8): deep = {"not": deep}
try:
    evaluate_rules(deep, S); assert False
except RuleError: pass
# 8. between + type mismatch handled
ok, _ = evaluate_rules({"all":[{"field":"tenth_pct","op":"between","value":[80,95]}]}, S); assert ok
ok, r = evaluate_rules({"all":[{"field":"branch","op":">=","value":5,"label":"Branch"}]}, S)
assert not ok and "unexpected format" in r[0]
print("evaluator: 8/8 passed")

# ---- policy templates ----
# no offers => always allowed
assert check_policy({"one_offer": True}, [], 800000) == (True, None)
# one-offer rule blocks
ok, why = check_policy({"one_offer": True}, [{"package":600000}], 2000000)
assert not ok and "one offer" in why
# multiplier: 6L best, 1.5x => needs >=9L
ok, why = check_policy({"upgrade":"multiplier","multiplier":1.5}, [{"package":600000}], 800000)
assert not ok and "1.5x" in why
ok, _ = check_policy({"upgrade":"multiplier","multiplier":1.5}, [{"package":600000}], 1200000)
assert ok
# slabs: placed 6L (S2 of <=5,<=10,open) => only S3 (>10L) allowed
pol = {"upgrade":"higher_slab","slabs":[{"name":"S1","max_lpa":5},{"name":"S2","max_lpa":10},{"name":"S3"}]}
ok, why = check_policy(pol, [{"package":600000}], 900000)
assert not ok and "S2" in why
ok, _ = check_policy(pol, [{"package":600000}], 1800000)
assert ok
# max offers cap
ok, why = check_policy({"max_offers":2}, [{"package":1},{"package":2}], 999999999)
assert not ok and "maximum 2" in why
print("policy: 7/7 passed")

# ---- legacy bridge ----
lr = legacy_rules_from_columns({"min_cgpa": 7.0, "max_backlogs": 1, "eligible_branches": ["CSE"]})
ok, _ = evaluate_rules(lr, S); assert ok
ok, r = evaluate_rules(lr, {**S, "branch": "MECH"}); assert not ok and "Branch" in r[0]
print("legacy bridge: 2/2 passed")
print("\nALL ELIGIBILITY TESTS PASSED")
