# Run from backend/: PYTHONPATH=. python3 tests/test_google_sso.py (needs the seeded local DB)
"""Google SSO path test: substitutes the token verifier (the only piece that
needs Google's servers) and exercises everything after it for real —
tenant matching, auto-provisioning, linking, and the failure paths."""
import os
os.environ["DATABASE_URL"] = "postgresql+psycopg://app_user:x@127.0.0.1:5432/poc"
os.environ["JWT_SECRET"] = "test-secret"
os.environ["DEV_FALLBACK"] = "false"
os.environ["GOOGLE_CLIENT_ID"] = "test-client-id.apps.googleusercontent.com"

from fastapi.testclient import TestClient
from app.main import app
from app.routers import auth_routes

client = TestClient(app)

def fake_verify_factory(email, verified=True, sub="gsub-123", name="G User"):
    def _fake(credential):
        return {"email": email, "email_verified": verified, "sub": sub, "name": name}
    return _fake

# 1. unknown email -> 403 (no roster/membership match)
auth_routes.google_verify = fake_verify_factory("stranger@nowhere.com")
r = client.post("/api/auth/google", json={"credential": "x"})
assert r.status_code == 403, r.text
print("1. unknown email -> 403                       OK")

# 2. unverified email -> 401
auth_routes.google_verify = fake_verify_factory("student5@demo.ac.in", verified=False)
r = client.post("/api/auth/google", json={"credential": "x"})
assert r.status_code == 401, r.text
print("2. unverified google email -> 401             OK")

# 3. roster student, first sign-in -> auto-provision + student token
auth_routes.google_verify = fake_verify_factory("student5@demo.ac.in", sub="gsub-s5")
r = client.post("/api/auth/google", json={"credential": "x"})
assert r.status_code == 200, r.text
d = r.json()
assert d["role"] == "student" and d["college_id"] == 1
print("3. roster match -> auto-provisioned student   OK")

# 4. same student signs in again -> same user id (idempotent link)
uid_first = d["user"]["id"]
r = client.post("/api/auth/google", json={"credential": "x"})
assert r.json()["user"]["id"] == uid_first
print("4. repeat google sign-in -> same account      OK")

# 5. admin via google (membership email match) -> admin token
auth_routes.google_verify = fake_verify_factory("admin@demo.ac.in", sub="gsub-adm")
r = client.post("/api/auth/google", json={"credential": "x"})
assert r.status_code == 200 and r.json()["role"] == "admin", r.text
print("5. membership email -> admin via google       OK")

print("\nALL GOOGLE-PATH TESTS PASSED")
