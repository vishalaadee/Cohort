# College Partnership Agreement — Data Clause Template

> **Disclaimer:** This is a template, not legal advice. Get it reviewed by a
> lawyer before using it in a real agreement. The DPDP Act (2023) rules are
> still evolving — the final rules gazette may change specific requirements.

---

## Schedule B: Data Collection, Use, and Sharing

### 1. Data collected

The Platform collects the following categories of student data through the
College's official placement process:

- **Identity data:** full name, roll number, email address, branch, batch
- **Academic data:** CGPA, backlogs, 10th/12th percentages, other academic
  metrics as defined by the College's attribute registry
- **Career data:** resume (PDF), placement applications, interview outcomes,
  feedback/experience write-ups, coding profile links (voluntarily provided)
- **Derived data:** Cohort Score (a computed, explainable talent signal based
  on the above inputs)

### 2. Consent architecture

Data collection follows a **two-tier consent model**:

**Tier 1 — College-level (this Agreement):**
The College authorises the Platform to collect and process the above data for
the purpose of managing the College's campus placement process. This is the
lawful basis for processing under DPDP Section 4(1) — performance of a
contract (this Agreement) and legitimate interest of the College.

**Tier 2 — Student-level (in-product opt-in):**
Sharing of a student's profile with recruiters outside the College's own
placement process requires the student's explicit, informed, revocable
consent, collected in-product as a togglable opt-in ("Share my verified
profile with recruiters on Cohort"). Students who do not opt in are fully
functional within their College's placement portal but invisible to external
recruiters. Consent status is logged with timestamp and is revocable at any
time.

### 3. Data ownership

- **Raw student data** (name, CGPA, resume, etc.) is owned by the student.
- **Aggregated, anonymised placement statistics** (branch-wise rates, package
  distributions, funnel metrics) may be used by the Platform for benchmarking,
  marketing, and product improvement, provided no individual student is
  identifiable. The College is entitled to the same aggregated data for its
  accreditation and reporting purposes.
- **The Cohort Score** is computed by the Platform and is a Platform asset.
  The College and the student both have read access to it. It is shared with
  recruiters only when Tier 2 consent is active.
- **Interview experience write-ups** submitted by students are licensed to the
  Platform for display to other students on the Platform (the educational
  purpose for which they were submitted), and may be shared with recruiter
  partners only in anonymised, aggregated form.

### 4. Recruiter data sharing

The Platform may share **opted-in student profiles** with recruiter partners
for the purpose of matching students with job opportunities. Such sharing is:
- limited to students who have active Tier 2 consent,
- restricted to the data categories listed in §1,
- logged (which recruiter accessed which profile, when),
- subject to the Platform's recruiter terms of service, which prohibit
  re-selling, scraping, or contacting students outside the Platform.

The College shall be notified before any new recruiter partner category is
added (e.g., staffing agencies vs. direct employers).

### 5. Data retention and deletion

- Active student data is retained for the duration of the student's
  enrolment plus 2 years (to support alumni features and outcome tracking).
- Upon a student's deletion request (DPDP right to erasure), the Platform
  deletes personal data within 30 days. Anonymised aggregate statistics
  (which cannot identify the student) are retained.
- Upon termination of this Agreement, the College may request a full export
  of its placement data in machine-readable format (CSV/JSON) within 60 days,
  after which the Platform deletes College-specific data.

### 6. Security

The Platform implements: tenant isolation via PostgreSQL Row-Level Security
(each college's data is cryptographically inaccessible to other colleges),
encryption at rest (RDS), encryption in transit (TLS), bcrypt password
hashing, and scoped RBAC (5-role model). Annual security review findings are
shared with the College upon request.

### 7. DPDP compliance

Both parties commit to compliance with the Digital Personal Data Protection
Act, 2023 and any rules made thereunder. The Platform shall:
- maintain a privacy policy accessible to students,
- honour data principal rights (access, correction, erasure, grievance),
- appoint a Grievance Officer and share contact details with the College,
- report data breaches to the College and the Data Protection Board within
  the timelines prescribed by the Act.

---

**For the College:**

Name: ___________________________  Designation: ___________________________

Signature: ________________________  Date: ___________________________

**For Cohort:**

Name: ___________________________  Designation: ___________________________

Signature: ________________________  Date: ___________________________
