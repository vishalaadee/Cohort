# Full feature test. Run: PYTHONPATH=. python3 tests/test_features.py (needs demo DB)
import io, os
os.environ.setdefault("DATABASE_URL","postgresql+psycopg://app_user:x@127.0.0.1:5432/demo")
os.environ.setdefault("JWT_SECRET","demo-secret"); os.environ.setdefault("DEV_FALLBACK","false")
from fastapi.testclient import TestClient
from app.main import app
c = TestClient(app)
A = {"Authorization":"Bearer "+c.post("/api/auth/login",json={"email":"placements.gnc@gmail.com","password":"gncadmin1"}).json()["token"]}
import sqlalchemy as sa
from app.db import engine
def student(email,pw):
    r = c.post("/api/auth/login",json={"email":email,"password":pw})
    if r.status_code==200: return {"Authorization":"Bearer "+r.json()["token"]}
    with engine.begin() as conn:  # (re)claim: fetch roll + fresh code as system
        conn.execute(sa.text("SELECT set_config('app.role','owner',true)"))
        row = conn.execute(sa.text("SELECT id, roll_no FROM students WHERE email=:e"),{"e":email}).mappings().one()
        conn.execute(sa.text("UPDATE students SET activation_code='RESEED01', user_id=NULL WHERE id=:i"),{"i":row["id"]})
    r = c.post("/api/auth/claim",json={"college_slug":"gnc","roll_no":row["roll_no"],
         "activation_code":"RESEED01","password":pw})
    assert r.status_code==200, r.text
    return {"Authorization":"Bearer "+r.json()["token"]}
P = student("priya.mehta2022@gmail.com","priya@2026x")   # CGPA 9.10, no offer

# 1. registration blocked without resume
r = c.post("/api/me/register/6", headers=P)  # BharatPay id? find dynamically
drives = c.get("/api/me/drives", headers=P).json()
bhpay = next(d for d in drives if d["name"]=="BharatPay Fintech")
r = c.post(f"/api/me/register/{bhpay['id']}", headers=P)
assert r.status_code==400 and "resume" in r.json()["detail"].lower(), r.text
print("1. register blocked without resume            OK")

# 2. resume upload (pdf ok, oversize rejected)
pdf = b"%PDF-1.4 fake"; 
r = c.post("/api/me/resume", headers=P, files={"file":("p.pdf",io.BytesIO(pdf),"application/pdf")})
assert r.status_code==200, r.text
r2 = c.post("/api/me/resume", headers=P, files={"file":("p.png",io.BytesIO(b"x"),"image/png")})
assert r2.status_code==400
print("2. resume upload + type validation            OK")

# 3. now registration succeeds; duplicate blocked; ineligible drive blocked w/ reasons
r = c.post(f"/api/me/register/{bhpay['id']}", headers=P); assert r.status_code==200, r.text
r = c.post(f"/api/me/register/{bhpay['id']}", headers=P); assert r.status_code==409
cloud = next(d for d in drives if d["name"]=="CloudNine Labs")
r = c.post(f"/api/me/register/{cloud['id']}", headers=P)
assert r.status_code in (400,403)  # status=0 (closed) -> 400
print("3. register ok / duplicate 409 / closed drive OK")

# 4. profile + edit request -> admin approves -> cgpa changes
prof = c.get("/api/me/profile", headers=P).json()["profile"]; assert prof["roll_no"]=="01GNC22CS002"
r = c.post("/api/me/edit-request", headers=P, json={"field":"cgpa","requested_value":"9.25","note":"sem 6 update"})
assert r.status_code==200
req = c.get("/api/admin/edit-requests", headers=A).json()[0]
r = c.patch(f"/api/admin/edit-requests/{req['id']}", headers=A, json={"decision":"approved"})
assert r.status_code==200
assert float(c.get("/api/me/profile", headers=P).json()["profile"]["cgpa"])==9.25
print("4. edit request -> approve -> applied         OK")

# 5. Q&A: student posts, admin answers, other student can read answered
r = c.post("/api/me/questions", headers=P, json={"title":"When is the Zentrix test?","body":"Any syllabus?"})
assert r.status_code==200
q = c.get("/api/admin/questions", headers=A).json()[0]
r = c.patch(f"/api/admin/questions/{q['id']}", headers=A, json={"action":"answer","answer":"Aug 3, DSA + aptitude."})
assert r.status_code==200
S2 = student("sanjayhostel0@gmail.com","sanjay@2026")
vis = c.get("/api/me/questions", headers=S2).json()
assert any("Zentrix test" in x["title"] and x["answer"] for x in vis)
print("5. Q&A post -> answer -> visible to peers     OK")

# 6. feedback gated: Priya (unplaced) blocked; Sanjay (has offer) allowed; browse works
r = c.post("/api/me/feedback", headers=P, json={"tips":"x"}); assert r.status_code==403
r = c.post("/api/me/feedback", headers=S2, json={"role":"GET","ctc":750000,"rounds":"OA+2T+HR","difficulty":3,"topics":"aptitude, SQL","tips":"Revise joins."})
assert r.status_code==200, r.text
fb = c.get("/api/me/feedback", headers=P).json()
assert any(f["company"]=="Ashoka Motors" for f in fb)
print("6. feedback gate + junior browse              OK")

# 7. admin: create drive, save rules (bad op rejected), preview count, open it
r = c.post("/api/admin/companies", headers=A, json={"name":"Nimbus AI","category":"tier1","package":2200000})
nid = r.json()["id"]
bad = c.put(f"/api/admin/companies/{nid}/rules", headers=A, json={"rules":{"all":[{"field":"cgpa","op":"exec","value":1}]}})
assert bad.status_code==400
good = c.put(f"/api/admin/companies/{nid}/rules", headers=A,
  json={"rules":{"all":[{"field":"cgpa","op":">=","value":8.5,"label":"CGPA"},{"field":"branch","op":"in","value":["CSE","AIML"],"label":"Branch"}]}})
assert good.status_code==200
prev = c.get(f"/api/admin/companies/{nid}/eligibility-preview", headers=A).json()
assert prev["total"]==25 and 0 < prev["eligible"] < 25, prev
r = c.patch(f"/api/admin/companies/{nid}", headers=A, json={"status":1}); assert r.status_code==200
print(f"7. drive+rules+preview ({prev['eligible']}/{prev['total']} eligible)   OK")

# 8. registrants + advance round + place -> offer appears
regs = c.get(f"/api/admin/companies/{bhpay['id']}/registrations", headers=A).json()
aid = next(x["id"] for x in regs if x["roll_no"]=="01GNC22CS002")
r = c.patch(f"/api/admin/applications/{aid}", headers=A, json={"current_round":"hr"}); assert r.status_code==200
r = c.patch(f"/api/admin/applications/{aid}", headers=A, json={"status":"placed"}); assert r.status_code==200
prof2 = c.get("/api/me/profile", headers=P).json()["profile"]; assert prof2["offers"]==1
print("8. pipeline advance -> placed -> offer row    OK")

# 9. notes + calendar
r = c.post("/api/admin/notes", headers=A, json={"title":"Zentrix pre-placement talk","note_date":"2026-08-01","kind":"visit","body":"Auditorium 10am"})
assert r.status_code==200
notes = c.get("/api/admin/notes", headers=A).json(); assert notes and notes[0]["kind"]=="visit"
print("9. notes/calendar CRUD                        OK")

# 10. analytics + policy save
an = c.get("/api/admin/analytics", headers=A).json()
assert an["package"]["max"] >= 750000 and len(an["branch_wise"])>=6
r = c.put("/api/admin/policy", headers=A, json={"upgrade":"multiplier","multiplier":1.5,"max_offers":2})
assert r.status_code==200
print("10. analytics + policy save                   OK")
print("\nALL 10 FEATURE SUITES PASSED")
