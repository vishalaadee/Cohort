# Quickstart — from zero to a working college in ~20 minutes

Uses the bundled dummy data: `roster-gnc.csv` (25 students) and
`gnc-college-setup.sql` (the college + admin + 4 drives). Works identically
locally and on AWS.

## 1. Bring the stack up

**Local:**
```bash
cp .env.example .env        # set JWT_SECRET + passwords
cd infra && docker compose up -d --build
```
**AWS:** follow docs/INFRA.md §3–6 (RDS + EC2 + `docker-compose.aws.yml`),
then continue here — steps 2 onward are the same.

## 2. Create the college (one-time SQL)

Generate the admin password hash on your laptop:
```bash
python3 -c "import bcrypt;print(bcrypt.hashpw(b'gncadmin1',bcrypt.gensalt()).decode())"
```
Open `gnc-college-setup.sql`, paste the hash over the `REPLACE_ME` placeholder,
then run the whole file against the database:
- **Local:** `docker exec -i infra-db-1 psql -U postgres -d placement < gnc-college-setup.sql`
- **AWS:** run it in DBeaver (connected through the SSH tunnel, docs/INFRA.md §5)

This creates: Greenfield National College (slug `gnc`), the placement-officer
login, and 4 drives (Zentrix, BharatPay, Ashoka, CloudNine).

## 3. Sign in as the placement officer

Open `http://localhost/app` (or your Elastic IP / domain).
Email `placements.gnc@gmail.com` · password `gncadmin1`.

## 4. Set the placement policy (once)

Sidebar → **Placement policy** → upgrade rule = *Multiplier*, value `1.5` →
Save. This now applies to every drive automatically — you never set it again.

## 5. Import the roster

Sidebar → **Import roster** → drop `roster-gnc.csv` → you'll see
*25 imported · 6 branches created* → click **Download activation codes**.
That CSV is what you hand to students (in real life: mail-merge or print).

## 6. Configure a drive's eligibility

Sidebar → **Drives** → Zentrix → **Eligibility** → add conditions in the
builder → **Preview eligible count** (sanity-check before opening) → Save →
back → **Open**.

## 7. Onboard a student (the Sanjay walkthrough)

Log out → **Claim account** tab:
college `gnc` · roll `01GNC22CS001` · his activation code from step 5 ·
password of his choice. (Because his roster email is a Gmail —
`sanjayhostel0@gmail.com` — he could alternatively just hit *Continue with
Google* once `GOOGLE_CLIENT_ID` is configured, docs/USAGE.md §1.)

As Sanjay: **Profile** → upload any PDF as resume → **Drives** → see
eligible/blocked with reasons → **Register** on an eligible one.

## 8. Run the pipeline

Back as the officer: **Drives → Pipeline** → advance Sanjay's round via the
dropdown → set status **placed** → the offer is recorded automatically,
**Analytics** updates, and Sanjay's **Feedback** section unlocks.

That's the full loop: policy → roster → drive → register → rounds → placed →
analytics → feedback. Repeat step 5 with your real roster CSV when ready.

## Demo credentials summary

| Who | Email | Password |
|---|---|---|
| GNC placement officer | placements.gnc@gmail.com | gncadmin1 |
| Student (after claim) | sanjayhostel0@gmail.com | whatever they chose |
| Demo college #1 admin | admin@demo.ac.in | demo1234 |

**Delete the demo college and change all passwords before importing real
student data.**
