# Student portal audit — endpoint by endpoint

You were right that my focus had scattered. My earlier audit checked the code
*I* had written and took the pre-existing endpoints on trust. This one goes
through every student-facing route and every query behind it.

**16 bugs found. Two of them leak one student's data to another.**

---

## The systemic problem

Three endpoints carried **no `WHERE` clause** and a comment saying row-level
security would scope them to the caller:

```python
@router.get("/questions")
def my_questions(claims):
    # RLS shows: own questions + all answered ones (college-wide learning)
    rows = conn.execute(text("SELECT ... FROM questions ORDER BY created_at DESC LIMIT 200"))
```

The policies on `questions`, `edit_requests` and `applications` are
**college-scoped, not user-scoped**. So "my questions" returned the whole
college's. Proven against a database with two students in one college:

```
Student B asks for "my questions"
  OLD (no WHERE, trusting RLS):
    sees: my cgpa is 8.7 still why am i not eligible     <- student A's
    sees: can i sit for two dream companies
  NEW (explicit student_id filter):
    sees: can i sit for two dream companies
```

That first line is the screenshot you sent — one student's marks on another
student's screen. Same for correction requests, which carry names, marks and
email addresses.

This is the same class as the F-6 `round_progress` bug that `0008` fixed. These
three were missed because `round_progress` was found by reading policies, and
nobody re-read the *queries* that assumed those policies did more than they do.

**A comment is not a filter.** Every student-owned query now resolves the
caller's `students.id` through one helper and filters on it explicitly. RLS
remains the backstop, not the only line.

---

## Backend — `portal.py`

| # | Endpoint | Bug | Severity |
|---|---|---|---|
| 1 | `GET /questions` | No filter — every student saw every student's questions | **Leak** |
| 2 | `GET /profile` | `edit_requests` unfiltered — saw the college's correction requests | **Leak** |
| 3 | `GET /applications` | Relied on RLS to self-scope; now explicit | High |
| 4 | `GET /profile` | Never returned `has_resume` — the app reads it in 3 places | High |
| 5 | `GET /resume/download` | Did not exist — no way to see your own resume | High |
| 6 | `GET /drives` | No deadline filter — expired drives shown with a live Apply button | High |
| 7 | `GET /drives` | No `applied` flag — Apply shown on drives already applied to | Medium |
| 8 | `GET /applications` | Missing `company_id`, which the feedback form needs | Medium |
| 9 | `GET /resume` | No role check; every other student route has one | Low |
| 10 | `GET /feedback` | No role check | Low |

`GET /feedback` stays college-wide **by design** and is now commented as such,
so the next audit doesn't "fix" it. The difference from `/questions` is
consent: an experience is written in order to be published to juniors, and the
author chose what went in it. A question is someone describing their own
problem to the placement cell. No student identity is selected in either case.

### `/drives`, before and after

```
OLD (status = 1 only)          NEW (status = 1 AND deadline in future)
  Rubicon  (open)                Rubicon  applied=false files=true
  Nova     (EXPIRED)             Beacon   applied=true  files=false
  Beacon   (applied)
```

Nova's deadline passed two days ago; it was still listed with an Apply button
that `POST /register` would then refuse. Kessel is a draft and correctly hidden
in both — the F-2 fix holds.

### On applying without a resume

The gate **does** exist in `POST /register` and is correct:

```python
has_resume = conn.execute(text("SELECT 1 FROM resumes WHERE student_id = :sid"), ...)
if not has_resume:
    raise HTTPException(400, "Upload your resume before registering ...")
```

What was broken is that the app could not *tell* you. `has_resume` was never
returned by `/profile`, so the profile card said "Not uploaded" whether or not
you had one, and the to-do list nagged permanently. If you got through without
one, a resume row existed from earlier testing — the server would have refused
otherwise. Worth confirming on your data:

```sql
SELECT s.roll_no, (r.student_id IS NOT NULL) AS has_resume
  FROM students s LEFT JOIN resumes r ON r.student_id = s.id ORDER BY 1;
```

---

## Frontend — `app.html`

| # | Where | Bug |
|---|---|---|
| 11 | `ProfileView` | Read `p.full_name` when the API returns `{profile:{...}}` — **the entire profile page rendered blank** |
| 12 | Consent toggle | Sent `{consent: true}`; the API reads `payload.get("share")`. Turning it **on silently saved off** |
| 13 | Resume card | No View button, and state was driven by the missing `has_resume` |
| 14 | Experiences | "Write yours" shown to everyone; the 403 arrived after writing it |
| 15 | Drives | Apply shown on applied and expired drives |
| 16 | Sidebar | Showed "Signed in" — no name, no roll number |

Bug 11 explains what you saw with the resume: the upload succeeded, the toast
fired, then the page re-rendered from the wrong object and still said "Not
uploaded". Nothing about the upload was broken.

Bug 12 is the quiet one. Consent has been unsettable since it was written —
the switch moved, the toast said it worked, and the database recorded `false`
every time. For a field whose whole purpose is that the student decides, that
matters more than the others.

### What changed

- Profile reads `res.profile`, shows the resume filename and upload date, adds
  **View** (opens the actual stored PDF), and lists pending correction requests
  — which were being fetched and then thrown away.
- Upload toast names the file and size: `resume.pdf uploaded · 184 KB`.
- Drives gains a **You've applied** section; Apply never appears on something
  that will error. A 400/409 refreshes the list instead of re-enabling a dead
  button, and there's a **JD** button where files are attached.
- Experiences hides "Write yours" until an offer is recorded and says why.
- Sidebar shows `Name · roll number · branch · college`.

---

## Still open

**The planner 500.** `GET /api/calendar` errors rather than returning an empty
month — my earlier guess was wrong. It queries `company_notes`, which comes
from migration `0004` and is not in anything I have. Send either:

```bash
docker compose -f docker-compose.aws.yml logs --tail=200 backend | grep -B5 -A40 -i traceback | tail -60
# or
psql "..." -c "\d company_notes"
```

**`not_in` for branches.** Left out of the branch picker until
`grep -n "not_in" backend/app/eligibility.py` confirms the engine evaluates it.

**Not yet audited:** `admin_extra.py`, `students_admin.py`, `companies.py`,
`dashboard.py`, `auth_routes.py` — the officer and CR side. Given what this
audit found in the student side, the same "no WHERE clause, trusting RLS"
pattern is likely there too. Send those files and I'll do the same pass. The
one I'd check first is anything a **CR** can call: a CR is branch-scoped, and
if those queries also assume RLS enforces the branch boundary, a CR is seeing
the whole college.
