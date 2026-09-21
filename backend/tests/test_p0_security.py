# P0 regression coverage. Run from backend/ against the local seeded database:
#   PYTHONPATH=. python3 tests/test_p0_security.py
import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://app_user:x@127.0.0.1:5432/placement")
os.environ.setdefault("JWT_SECRET", "demo-secret")
os.environ.setdefault("DEV_FALLBACK", "false")

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app
from app.db import engine
from app.security import create_token, hash_password

client = TestClient(app)


def owner_connection():
    conn = engine.connect()
    tx = conn.begin()
    conn.execute(text("SELECT set_config('app.role', 'owner', true)"))
    return conn, tx


def header(user_id, role, college_id, branch_id=None):
    token = create_token(user_id=user_id, role=role, college_id=college_id, branch_id=branch_id)
    return {"Authorization": f"Bearer {token}"}


# Make a stable, isolated second tenant and a CR in the demo college.  The
# direct setup connection uses the explicit system owner scope, never an API.
conn, tx = owner_connection()
try:
    second_college = conn.execute(text("""
        INSERT INTO colleges (name, slug, status)
        VALUES ('P0 Isolation College', 'p0-isolation', 'active')
        ON CONFLICT (slug) DO UPDATE SET name=EXCLUDED.name
        RETURNING id
    """)).scalar_one()
    second_branch = conn.execute(text("""
        INSERT INTO branches (college_id, code, name)
        VALUES (:college, 'CSE', 'Computer Science')
        ON CONFLICT (college_id, code) DO UPDATE SET name=EXCLUDED.name
        RETURNING id
    """), {"college": second_college}).scalar_one()

    second_user = conn.execute(text("""
        INSERT INTO users (email, full_name, password_hash)
        VALUES ('p0-isolation-admin@example.test', 'Isolation Admin', :hash)
        ON CONFLICT (email) DO UPDATE SET full_name=EXCLUDED.full_name
        RETURNING id
    """), {"hash": hash_password("not-used-in-this-test")}).scalar_one()
    conn.execute(text("""
        INSERT INTO memberships (user_id, college_id, role, status)
        VALUES (:user_id, :college_id, 'admin', 'active')
        ON CONFLICT (user_id, college_id, role) DO UPDATE SET status='active'
    """), {"user_id": second_user, "college_id": second_college})

    student = conn.execute(text("""
        SELECT id, user_id, college_id, branch_id
        FROM students WHERE user_id IS NOT NULL ORDER BY id LIMIT 1
    """)).mappings().one()
    cr_user = conn.execute(text("""
        INSERT INTO users (email, full_name, password_hash)
        VALUES ('p0-branch-cr@example.test', 'P0 Branch CR', :hash)
        ON CONFLICT (email) DO UPDATE SET full_name=EXCLUDED.full_name
        RETURNING id
    """), {"hash": hash_password("not-used-in-this-test")}).scalar_one()
    conn.execute(text("""
        INSERT INTO memberships (user_id, college_id, branch_id, role, status)
        VALUES (:user_id, :college_id, :branch_id, 'sub_admin', 'active')
        ON CONFLICT (user_id, college_id, role)
        DO UPDATE SET branch_id=EXCLUDED.branch_id, status='active'
    """), {"user_id": cr_user, "college_id": student["college_id"], "branch_id": student["branch_id"]})
finally:
    tx.commit()
    conn.close()

student_headers = header(student["user_id"], "student", student["college_id"], student["branch_id"])
cr_headers = header(cr_user, "sub_admin", student["college_id"], student["branch_id"])
admin_headers = header(1, "admin", student["college_id"])
other_admin_headers = header(second_user, "admin", second_college, second_branch)

# 1. Validation is structured and never the raw FastAPI validation list.
response = client.post("/api/auth/login", json={})
assert response.status_code == 422, response.text
error = response.json()["error"]
assert error["code"] == "validation_error" and error["fields"]["email"] == "This field is required."
print("1. safe 422 error contract                         OK")

# 2. Missing credentials are an explicit 401, not a successful empty list.
response = client.get("/api/companies")
assert response.status_code == 401 and response.json()["error"]["code"] == "authentication_required", response.text
print("2. unauthenticated requests rejected               OK")

# 3. A student asks a question, their CR escalates it, and the placement
# officer receives a durable inbox item.
title = "P0 escalation: when is the aptitude test?"
response = client.post("/api/me/questions", headers=student_headers, json={"title": title, "body": "Need confirmation."})
assert response.status_code == 200, response.text
questions = client.get("/api/admin/questions", headers=cr_headers).json()
question = next(item for item in questions if item["title"] == title)
response = client.patch(f"/api/admin/questions/{question['id']}", headers=cr_headers, json={"action": "escalate"})
assert response.status_code == 200, response.text
notifications = client.get("/api/admin/notifications", headers=admin_headers)
assert notifications.status_code == 200, notifications.text
notification = next(item for item in notifications.json() if item["resource_id"] == question["id"])
assert notification["kind"] == "question_escalated" and notification["read_at"] is None
print("3. CR escalation creates placement-officer inbox   OK")

# 4. Tenant/role boundaries: the other college cannot see or change the
# question, and a CR cannot perform placement-officer-only operations.
assert client.get("/api/admin/notifications", headers=other_admin_headers).json() == []
assert client.patch(f"/api/admin/questions/{question['id']}", headers=other_admin_headers,
                    json={"action": "answer", "answer": "Cross-tenant attempt"}).status_code == 404
assert client.post("/api/admin/companies", headers=cr_headers, json={"name": "Nope"}).status_code == 403
assert client.get("/api/admin/students/activation-codes", headers=cr_headers).status_code == 403
assert client.get("/api/admin/analytics", headers=cr_headers).status_code == 403
assert client.patch(f"/api/admin/applications/{question['id']}", headers=cr_headers,
                    json={"status": "placed"}).status_code == 403
print("4. cross-tenant and CR permissions enforced        OK")

# 5. Answering clears the actionable notification for the PO.
response = client.patch(f"/api/admin/questions/{question['id']}", headers=admin_headers,
                        json={"action": "answer", "answer": "The aptitude test is Friday."})
assert response.status_code == 200, response.text
updated = next(item for item in client.get("/api/admin/notifications", headers=admin_headers).json()
               if item["id"] == notification["id"])
assert updated["read_at"] is not None and updated["question_status"] == "answered"
print("5. PO answer resolves the escalation notification  OK")

print("\nALL P0 SECURITY TESTS PASSED")
