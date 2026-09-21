# Go-to-market and rollout

How to get from zero colleges to a network, in an order that doesn't require believing anything unproven. Written September 2026; the calendar assumptions below are the most time-sensitive part of this document.

Every number here is a **hypothesis to validate**, not a fact. Where something needs checking against a real college before you rely on it, it says so.

---

## 1. The timing problem, first

Indian engineering placement seasons run roughly **July/August to December**, with a tail into March. Institutional budget and procurement decisions cluster in **February to June**, ahead of the new academic year.

That has one hard consequence: **a platform that isn't live by August has no season data until the following August.** It is September 2026. The 2026–27 season is already underway.

So the realistic calendar is:

| Window | What it's for |
|---|---|
| **Sep 2026 – Jan 2027** | Design-partner phase. One to three colleges, running the platform *alongside* their existing process, or for a subset of drives. The goal is not revenue — it's watching real drives happen and fixing what breaks. |
| **Feb – Jun 2027** | Sales window. This is when colleges decide and budget. Everything you learned from the design partners becomes the pitch. |
| **Jul – Aug 2027** | Onboarding window. Roster imports, account claims, officer training, before the season starts. |
| **Aug 2027 – Mar 2028** | First real season at scale. This is the season that produces your case studies, your data, and your renewals. |

Trying to compress this — selling hard in November to a college mid-season — mostly fails, because nobody switches placement systems in the middle of a placement season. Use the current season to *earn the right* to sell in February.

---

## 2. Who to sell to

### The ICP

A private or autonomous engineering college or university, **500–5,000 students**, Tier-2 or Tier-3 city, where:

- the placement office is one to three people, and the head often teaches as well
- operations run on Excel, WhatsApp groups and Google Forms
- CRs do significant operational legwork
- there is no internal software team that will build and *maintain* a portal
- management wants placement numbers for accreditation and for marketing to next year's admissions
- enterprise campus-hiring platforms feel expensive, over-featured and impersonal

The disqualifiers matter as much as the qualifiers. **Avoid** for now: IITs/NITs and top-tier private universities (already served, long procurement, high expectations), colleges under 300 students (the pain is real but the budget isn't), and any college whose placement cell is one person who is retiring — you need a champion who will still be there next season.

### The decision unit

Four people, and the mistake is talking to only the first one:

| Role | Cares about | Says |
|---|---|---|
| **TPO / Placement Officer** | Their own daily workload | "This would save me hours" — the champion, but usually cannot sign |
| **Principal / Director** | Institutional reputation, accreditation, admissions | "Does this make our NAAC/NBA submission easier?" |
| **Management / Trustees** | Cost, and outcomes they can advertise | "What does this cost per student, and what do we get?" |
| **IT / systems person** | Whether they have to maintain it | "Where does the data live? Who supports it?" |

The TPO gets you in the door and the Principal signs. **Design your demo for the TPO and your one-pager for the Principal.**

---

## 3. The wedge: accreditation, not software

This is the most important commercial idea in this document.

Placement statistics are not just operational — they are **mandatory reporting**. NAAC institutional assessment includes student progression and placement outcomes; NBA program accreditation is outcome-based and includes placement; NIRF ranking submissions include graduation outcomes and placement/salary data; AICTE requires annual reporting. Every one of these needs placement numbers **by program, by year, with salary data**, assembled accurately and defensibly.

Today most colleges assemble that by hand, from spreadsheets and memory, in a panic, once a year — usually done by the same overloaded officer, often reconstructing data that was never properly recorded.

That reframes the entire sale:

> **Not:** "buy placement software, it's nicer than your spreadsheet."
> **But:** "every placement action your office takes this year is automatically recorded in the format your accreditation submission needs — and you can generate it in one click instead of three weeks."

Why this works commercially: it moves the budget line from the placement cell's small discretionary spend to the **institution's compliance and accreditation budget**, which is larger, less price-sensitive, and owned by the Principal — who is also the person who can actually sign. It also gives an answer to "why now": accreditation cycles have deadlines, and data you didn't record can't be reconstructed.

**Before relying on this, validate it properly.** Get the actual submission templates a real college used in its last NAAC/NBA/NIRF cycle, confirm which fields come from placement data, and build the export to match those formats exactly. Formats change between cycles, so this needs verifying against current requirements rather than assumed. If it holds, UC-38 in the use-case catalogue becomes the highest-ROI feature in the entire backlog.

---

## 4. Positioning against what exists

Established platforms — Superset being the most prominent — already run end-to-end campus hiring at large scale across many institutions, and already market enterprise security and compliance credentials. **Do not pitch "a common platform connecting colleges, students and companies."** That is their pitch, they got there first, and the response is a one-liner that ends your meeting.

Three positions that are actually defensible:

**"Built for how your office actually works."** Enterprise platforms are designed around the hiring event and the employer relationship. Your product is designed around the placement officer's week: the WhatsApp messages, the eligibility arguments, the CR delegation, the chasing. That's a different product, not a cheaper version of the same one.

**"Eligibility that explains itself."** The rule engine already produces human-readable reasons — "CGPA is 6.8; needs to be at least 7.0." That single capability eliminates the highest-volume, lowest-value conversation in a placement office. In a demo, show a student's screen saying *why* they aren't eligible for three drives. This lands harder than any dashboard.

**"Your CRs, with guardrails."** The delegation model — configurable, scoped capabilities with a hierarchy that cannot be escalated — is specific to how Indian colleges actually run placements, with student representatives doing operational work. Platforms designed around corporate recruiters don't model this well.

And when the "why not just build it ourselves?" objection comes — it will — the honest answer is not that they can't. It's: *you can build v1 in a semester. The cost is v2, and the security, and the person who maintains it after the student who wrote it graduates. We're already past v1, and it improves every month whether or not anyone at your college has time.*

---

## 5. Rollout sequence, with gates

Each stage has an exit gate. **Do not start the next stage until the gate is met** — this is the discipline that prevents the classic failure of scaling a product nobody actually uses.

### Stage 0 — Design partners (now → Jan 2027) · target: 1–3 colleges

Not customers. Partners. Ideally free or near-free, in exchange for genuine access.

What to actually do: sit in the placement office during a real drive. Don't ask "what features do you want" — ask "show me how you ran the last drive," and then watch. Watch the spreadsheet, the WhatsApp broadcast, the manual eligibility check, the phone calls to students who didn't reply, the moment someone realises a student was left off the shortlist. Note every copy-paste. Every copy-paste is a feature.

**Gate to Stage 1:** at least one complete drive run end-to-end on the platform, from publish to offer recorded, with the officer choosing to use it rather than being asked to. Plus the P0 gaps closed (`USE_CASES.md` §2) and the High findings fixed (`SECURITY_REVIEW.md`).

### Stage 1 — First paying colleges (Feb → Aug 2027) · target: 5–10

**Charge from the first one, even if it's small.** A free pilot gets deprioritised the moment the officer is busy, which is exactly when you need them using it. A modest paid pilot creates the internal commitment that makes the pilot real. Price low, but not zero.

Sales motion is founder-led and referral-driven. TPOs in a region know each other and talk; there are also TPO associations and regional placement-officer networks worth being present in. One genuinely delighted TPO is worth more than any amount of outbound.

**Gate to Stage 2:** 5+ colleges renewed for a second season, at least 70% of drives at those colleges running on the platform rather than reverting to WhatsApp, and onboarding a new college taking under one day with zero engineering involvement (UC-09).

### Stage 2 — Repeatable sales (Aug 2027 → 2028) · target: 50

Now the motion can stop being purely founder-led: a documented onboarding runbook, a standard pilot structure, references by region and college type. Depth over breadth remains the rule — **50 colleges with clean, complete, trusted data is worth far more than 500 with partial adoption**, because the entire Phase 2 thesis depends on data quality, and partial adoption produces data that is worse than useless because it's misleadingly incomplete.

**Gate to Stage 3 (the Phase 2 gate):** 50+ colleges, two consecutive seasons of complete data, >85% of drives on-platform, renewal rate above 85%, and a student consent opt-in rate above 50% when asked honestly. If consent opt-in is low, the network thesis is wrong and should be revisited rather than forced.

### Stage 3 — The company side (2028+)

Covered in §6. Do not start early. The most common way this kind of company dies is building the marketplace before the operating system is indispensable.

---

## 6. The company side, and the cold-start solve

The chicken-and-egg problem is real: companies won't pay for access to a small candidate pool, and colleges won't join for companies that might arrive someday.

**The solve is that you don't have a cold start — you have a warm one you're ignoring.** The companies you want are *already visiting your colleges*. At 50 colleges you have hundreds of existing recruiter relationships running drives through email and spreadsheets.

So the first company-facing product is **not** discovery, search or subscriptions. It's a free coordination surface for drives they're already running:

- a link to view the shortlist, instead of a spreadsheet attachment
- upload results back, instead of emailing a marked-up file
- schedule interview slots, instead of a phone call chain
- see the process status without emailing the TPO

This is valuable to the company, costs them nothing, requires no sales cycle, and reduces the placement officer's workload — so the college pushes adoption for you. Every drive creates a company account as a **side effect of the college workflow**. After two seasons you have hundreds of company accounts with zero customer acquisition cost, and the relationships and usage data to know which ones would pay for more.

Only then does discovery make sense, and only then can you honestly say to a company: "you already run drives at 40 of our colleges — for a subscription, you can also find candidates at the other 60 who match what you actually hire."

**Pricing structure for that day** — charge for reach and tooling, not for candidates:

| Tier | Includes |
|---|---|
| Free | Drives at colleges that invited you; shortlists, scheduling, results |
| Growth | Search across consented candidates in a region; saved searches; outreach with limits |
| Enterprise | National reach, assessments, ATS integration, analytics, employer branding |

Deliberately **not** "pay more, get better students." That framing reads as auctioning students, will eventually generate a story that damages college trust, and is the fastest way to lose the consent rate the whole model depends on. Sell reach, tools and workflow. Let students opt into being discoverable, and let quality be the same for everyone.

---

## 7. Pricing the college side

The standard model in Indian institutional software is **per student per year**, because it scales with the college's own size and is easy to compare against a budget line.

A plausible starting hypothesis for this segment — to be tested, not assumed:

| Component | Hypothesis |
|---|---|
| Platform | ₹100–250 per student per year, tiered by size |
| Typical 1,500-student college | ₹1.5L–3.75L per year |
| Pilot season | Discounted heavily (50–70%), but never free |
| Accreditation export | Included — it's the reason they buy, not an upsell |
| Onboarding/migration | Free during Stages 0–1; a fee later, once it's repeatable |

Three principles: **annual billing aligned to the academic year**, not monthly — that's how institutional budgets work. **Never discount by removing security or support**; discount on price, not on the things that make the product trustworthy. And **price the second year at the real rate from the start**, disclosed up front — a pilot price that quietly triples at renewal poisons the relationship you spent a year building.

The comparison that wins the budget conversation isn't against other software. It's against the cost of the officer's time, plus the risk of an accreditation submission built on reconstructed data.

---

## 8. What to measure

Vanity metrics will mislead you here. Colleges signed says nothing; colleges *using it in the middle of a busy week* says everything.

| Metric | Why it's the one that matters |
|---|---|
| **Drives run end-to-end on-platform** (% of all drives that season) | The single best product-market-fit signal. A drive that reverts to WhatsApp is a feature gap with a name. |
| **WhatsApp displacement** — announcements sent through the platform vs the group | The literal thing you're replacing |
| Student account claim rate within 2 weeks of import | Onboarding health; below ~60% the student side is effectively unused |
| Time from drive creation to publish | Officer friction |
| Eligibility disputes per drive | Should trend to near zero — this is the explainability feature working |
| Officer weekly active use *outside* peak drive days | Whether it's a system of record or an event tool |
| Accreditation export generated (yes/no per college) | The strongest renewal predictor |
| Renewal rate by season | The only real verdict |
| Consent opt-in rate, asked honestly | The Phase 2 go/no-go |

Instrument these from the first design partner. Retrofitting analytics after the season is over means losing the season's evidence.

---

## 9. Risks, honestly

**A well-funded incumbent moves down-market.** The most likely serious threat. Mitigation is depth in a segment they'd have to restructure to serve, and switching costs built from accumulated historical data — a college with three years of placement history in your system will not move it.

**The champion leaves.** TPOs change. Mitigation: make the Principal a stakeholder via accreditation reporting, and make sure the data is visibly the college's, not the officer's.

**Consent rates come in low.** Then the network thesis is weaker than assumed and Phase 2 should be re-planned rather than pushed. This is a real possible outcome and it's better to discover it at 50 colleges than at 500.

**One security incident.** At scale, a single cross-tenant leak is existential — not because of the technical damage but because trust is the entire product. This is why the findings in `SECURITY_REVIEW.md` come before growth, not after.

**Building instead of selling.** Statistically the most likely failure mode for a technical founder. The codebase is already substantially ahead of the customer base. The next meaningful unit of progress is a real placement officer running a real drive — not another feature.

**Kill criteria, decided in advance:** if after a full season with three design partners no college runs the majority of its drives on the platform without prompting, the problem is the product or the segment — not the sales effort. Stop and re-examine rather than scaling the push.
