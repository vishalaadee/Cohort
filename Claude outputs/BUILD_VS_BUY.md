# Why in-house placement portals fail

Sales material for the objection that kills these deals: *"Why don't we just
build it ourselves? We have CS students."*

The honest answer is not that they can't. They can — and many do, and it works
for a while. The answer is what it looks like in year three.

**Use these as patterns, never as a named example.** "Here's what we find in
in-house portals" is industry expertise. "College X has hardcoded admin
passwords" is a grudge, it's a vulnerability disclosure about a live system
holding student data, and it makes every TPO in the room wonder what you'll say
about them. The generalised version is also more persuasive, because it says
*this will happen to you* rather than *this happened to someone else*.

---

## 1. The eight failure patterns

Each is real, each is invisible until it isn't, and each has a specific cost
you can put in front of a Principal.

### Pattern 1 — Tenancy by string matching

A portal serving several campuses stores which ones a drive belongs to as a
comma-separated list, and checks access with a substring match:

```python
Company.eligible_college_ids.contains(str(college_id))
```

College `1` matches `"1"`. It also matches the `1` inside `"11"`, `"12"`,
`"21"`. With three campuses you will never notice. At twelve, one campus
silently sees another's drives, packages and shortlists.

**What it costs:** a data leak between institutions that produces no error, no
log line and no complaint — until a company asks why a college that wasn't
invited sent candidates.

**The contrast:** every query is tenant-scoped at the database, enforced by the
database, not by a string comparison in application code. Verified by a test
that fails the build if any table is missing the boundary.

### Pattern 2 — Credentials in source

Mail passwords, admin logins, and the signing secret for authentication tokens,
all committed to the repository as default values.

The signing secret is the one that matters. Whoever holds it can mint a token
claiming to be an administrator — not for one campus, for every campus. No
password needed, no login attempt logged, nothing to detect.

**What it costs:** one repository leak, one departing student with a clone, one
laptop, and the whole system is open. And because the token is *valid*, the
audit log shows legitimate admin activity.

**The contrast:** secrets in environment configuration, rotatable without a
code change, and never printed into an error message.

### Pattern 3 — One copy of the rules per campus

Eligibility starts as one function. Campus two needs a slightly different offer
cap, so there's an `if`. Campus three needs another, so there's an `elif`.
Three years later there are three near-identical copies of a two-hundred-line
eligibility ladder, each subtly different, and nobody is sure which is correct.

**What it costs:** two students in the same situation at different campuses get
different answers, and no one can say which is the policy. Every new campus is
another branch. Changing the rule means changing it in three places and hoping.

**The contrast:** policy is data, not code. Each college configures its own caps
and buckets; the engine is one implementation everyone shares. A new college is
a row, not a release.

### Pattern 4 — Errors that vanish

```python
except:
    db.rollback()
```

A student registers for a drive. Something fails. They see nothing, the
registration isn't saved, and no trace is kept anywhere.

**What it costs:** the officer finds out on results day, when a student says
they registered and isn't on the list. There's no way to prove it either way,
so the officer takes the blame and adds them manually — which is now an
undocumented exception to the eligibility rules.

**The contrast:** failures are surfaced to the user in plain language and
recorded for the officer.

### Pattern 5 — Shared database connections

A single database session created once at import and reused by every concurrent
request. Under load, a failure in one student's request rolls back another
student's registration.

**What it costs:** corruption that only appears on the busiest day of the
season, and cannot be reproduced afterwards.

### Pattern 6 — Drafts that aren't drafts

A drive being prepared — package not final, eligibility not set — is visible to
students, because the query that lists drives has no status filter.

**What it costs:** students see a package figure that changes, or a drive that
never happens. Both cost the placement cell credibility it can't easily get
back, and generate a week of questions.

**The contrast:** published is a distinct, audited act. Until it happens, only
staff can see the drive at all — and it's checked server-side, not hidden in
the interface.

### Pattern 7 — No audit trail

Who published that drive? Who downloaded the student list with phone numbers
and CGPAs? Who changed the offer cap in October?

In most in-house portals there is no answer, because nobody thought to record
it while building the thing that was urgently needed.

**What it costs:** the day something goes wrong — a leaked candidate list, a
disputed eligibility decision, a student claiming they were unfairly excluded —
the placement office has no record and no defence.

**The contrast:** every publish, export, bulk update and policy change is
recorded with who, what and when, append-only.

### Pattern 8 — The maintenance cliff

This is the one to close on, because it's the one they already suspect.

The portal was built by two final-year students. They were good. They
graduated. The next batch didn't write it and won't touch it. It runs, nobody
understands it, and every change is a risk nobody wants to take.

**What it costs:** the software freezes on the day its authors left. Meanwhile
the rules change, the regulator's format changes, and the workarounds move back
into spreadsheets — which is where the college started.

---

## 2. The objection handler

When it comes — and it will, usually from the Principal or the IT person:

> **"Why don't we just build this ourselves?"**

Do not argue that they can't. They can, and saying otherwise insults the person
in the room whose students would build it.

> "You absolutely can, and honestly v1 isn't hard — a couple of good final-year
> students could have something working in a semester.
>
> The cost isn't v1. It's v2, and the security work, and the person who
> maintains it after the students who wrote it graduate. That's the part that
> doesn't get budgeted, because it isn't visible when you decide.
>
> We're past v2. It improves every month whether or not anyone at your college
> has time that month. And when the accreditation format changes, that's our
> problem to solve, not something your officer discovers in October."

Then stop talking. If they push on cost, the comparison isn't against other
software — it's against the officer's time plus the risk of an accreditation
submission built on reconstructed data.

---

## 3. The strongest version: offer to look

This is the best lead generator in the document, and it costs you an hour.

> "Would it help if I spent thirty minutes looking at your current portal? No
> charge, no obligation. I'll tell you what I find either way — including if
> it's fine."

Why it works:

- **It gets you in the door** without selling anything, so there's nothing to
  say no to.
- **It's the credential.** They cannot evaluate a placement platform, but they
  can absolutely evaluate whether you found something real in their system that
  nobody else spotted.
- **It surfaces the pain** rather than asserting it. A TPO reading your pitch
  thinks "ours is probably fine." A TPO watching you demonstrate that one
  campus can see another's shortlists is a different conversation, and it is
  their finding now, not your claim.
- **You will find something.** These patterns are near-universal in portals
  built this way. Not because anyone was careless — because the person building
  it was solving the urgent problem, alone, without review.

### Running it

Ask for read access, or just walk through it on a screen share. Look for:

1. How is one campus separated from another — where is that decision made?
2. Can a student see a drive before it's published?
3. Is there a record of who exported the student list?
4. Where do the mail credentials live?
5. What happens to a registration when something fails?
6. Can a CR do anything an officer can?
7. Who maintains it now, and who maintained it eighteen months ago?

### Reporting it

**Privately, in writing, to the TPO only.** Never in a room with an audience,
never in marketing material, never naming the college afterwards.

Three findings, no more. For each: what it is, what it could cost them, and how
to fix it *without you* — including the ones they can fix in an afternoon. Give
away the cheap fixes. It proves the report is an assessment rather than a sales
document, and the expensive ones are what you're for.

If you find something genuinely serious — cross-campus data exposure,
credentials in a public repository — tell them immediately and separately from
any commercial conversation. Do not let it look like leverage. That single
choice is what makes you the person they call next year, and it's also the
right thing to do.

---

## 4. Where this fits the pitch

This document handles one objection. It is not the pitch.

The pitch is still the accreditation wedge in `GTM_ROLLOUT.md` §3 — *every
placement action your office takes this year is recorded in the format your
NAAC/NBA submission needs, generated in one click instead of three weeks*. That
moves the budget line from the placement cell's discretionary spend to the
institution's compliance budget, and changes who signs.

Use build-vs-buy when they raise it, and the free look to get in the door.
Don't lead with either. Nobody buys software because their current one is bad —
they buy because something they must do anyway gets easier.

---

## 5. One thing to be careful about

You are about to sell trust. Everything above works only if you are visibly the
person who handles this well.

Which means: no named colleges, no screenshots of anyone's code, no "look what
I found" in a LinkedIn post. The moment a TPO suspects their system might end
up as someone else's slide, the free audit stops working — for you and for
everyone after you.

There's a version of this that's a war story at a conference and burns the
strategy. And a version that's a quiet paragraph in a report to one officer,
which builds a reputation that sells for years. They look similar from the
inside. They are not.
