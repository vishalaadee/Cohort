# Expansion beyond engineering placements

**Phase 3+. Nothing in this document should influence a decision made in the next eighteen months**, except the one small discipline in §5, which costs nothing today and saves a rewrite later.

This exists because the founder asked what the shape of a wider platform looks like. It is written to be read once, agreed in principle, and then put down.

---

## 1. Why this is dangerous to think about now

The most common way an ambitious platform dies is genericising too early. A system built to serve "any institution placing any candidate into any opportunity" is, in practice, a system that serves nobody particularly well — and it loses to the product that is unapologetically specific about one workflow.

Concretely, premature generalisation would mean: eligibility rules abstracted until a placement officer can no longer read them; "CGPA" becoming `attribute_3`; drives becoming "opportunity instances"; and a UI where nothing is called what the user calls it. That product cannot win a demo against a spreadsheet, let alone against an incumbent.

So the rule for the next two years is simple: **be specific, and keep the plumbing generic.** Say "CGPA", "branch", "drive" and "placement officer" everywhere a user can see. Keep those words out of identity, tenancy, permissions, consent and audit.

---

## 2. What generalises and what doesn't

| Layer | Generalises? | Why |
|---|---|---|
| Tenancy — tenant registry, RLS, context injection | **Fully** | A tenant is a tenant; nothing about it is engineering-specific |
| Identity — person, user, membership, role, capability | **Fully** | "Institution → staff → delegate → participant" is the same shape everywhere |
| Consent ledger | **Fully** | Purpose, scope, version, revocation — domain-independent |
| Audit log | **Fully** | Same |
| Rule engine | **Mostly** | Fields and vocabulary are domain-specific; the evaluator, operators and safety limits are not |
| Pipeline / stages | **Mostly** | Stage sequences differ wildly; the machinery of ordered, audited stage transitions doesn't |
| Notifications, documents, imports, analytics primitives | **Mostly** | Content differs, plumbing doesn't |
| Eligibility semantics (CGPA, backlogs, branch) | **No** | Meaningless outside engineering |
| Placement policy (slabs, one-offer, upgrade multipliers) | **No** | Extremely specific to Indian engineering campus placement |
| Round vocabulary, package/CTC framing, accreditation exports | **No** | Domain, and country, specific |

The dividing line is clean: **everything below the domain services layer generalises; the domain services do not.** That is exactly the boundary already drawn in `ARCHITECTURE.md` §3, which is convenient — the Phase 3 architecture is the Phase 1 architecture with a second domain on top of the same core.

---

## 3. Adjacency, in order

Ranked by how little would have to change, which is a better ordering principle than market size.

**Tier 1 — nearly the same product.** Pharmacy, nursing and allied health, MBA and commerce, and other professional programs at the same institutions you already serve. Same institution, same placement office, often the *same officer* covering multiple streams. Different eligibility vocabulary, different recruiter sets, sometimes licensure or clinical-hours requirements. Realistically this is configuration, not a new platform — and it may well arrive on its own, as a college you already serve asks you to cover their pharmacy block. Treat it as Phase 2.5, not Phase 3.

**Tier 2 — same shape, different institution.** Polytechnics and ITIs. Very large in number, genuinely underserved, and the pain is arguably worse. But budgets are much smaller, apprenticeship and NAPS-style placement differs structurally from campus drives, and the buyer is often a government or trust body with a procurement process rather than a Principal who can decide. A real market, but a different sales motion — treat as a separate business line with its own economics, not an extension of the same one.

**Tier 3 — same core, different domain.** Law (internships and chambers), hotel management, design, architecture. Each needs genuine domain work: portfolios, articleships, licensure. Only worth it if a specific, funded demand appears.

**Tier 4 — not a college at all.** Bootcamps, upskilling providers, apprenticeship programs, employer graduate schemes. This is where the shared core matters most and the domain overlap matters least. It is also where the incumbents are entirely different companies. Genuinely a separate product built on shared infrastructure.

---

## 4. Why a separate platform, not a configuration flag

When the second serious vertical arrives, the instinct will be to add a `vertical` column and branch on it. Resist that. The failure mode is well documented: conditional logic accumulates in every domain service, every test matrix doubles, the UI grows toggles for concepts most users don't have, and eventually nobody can safely change anything because every change touches every vertical.

The alternative that works:

```
                  ┌──────────────────────────────┐
                  │        SHARED CORE           │
                  │  tenancy · identity ·        │
                  │  permissions · consent ·     │
                  │  audit · rule evaluator ·    │
                  │  stage machinery · docs      │
                  └───────────┬──────────────────┘
            ┌─────────────────┼─────────────────┐
            ▼                 ▼                 ▼
    ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
    │ Campus       │  │ Skills /     │  │ Talent       │
    │ Placement OS │  │ Apprentice   │  │ Network      │
    │ (Phase 1)    │  │ (Phase 3)    │  │ (Phase 2)    │
    └──────────────┘  └──────────────┘  └──────────────┘
     own vocabulary,   own vocabulary,   consented,
     own UI, own       own UI, own       audited, reads
     domain rules      domain rules      across verticals
```

Separate products, separate vocabularies, separate interfaces, **one core and one identity**. A person who was a student and later an apprentice is the same `person` — which is the entire reason for ADR-05 and the only part of this that has to be decided early.

---

## 5. The only thing to do now

One discipline, applied from today, makes all of the above cheap later and costs essentially nothing:

**Keep engineering-placement vocabulary out of the core layers.** `persons`, `memberships`, `consent_events`, `audit_log`, the capability model and the rule evaluator must not contain the words `cgpa`, `backlogs`, `branch`, `drive`, `package` or `placement`. Those belong in domain tables and domain services, where they should be used freely and prominently.

Two examples of getting it right, already visible in the current code: `eligibility.py` evaluates `{"field": ..., "op": ..., "value": ...}` — the evaluator has no idea what a CGPA is, and the field names arrive as data. And `attribute_defs` lets a college define its own fields rather than the schema hardcoding them. Both of those are already domain-agnostic machinery serving a domain-specific product. That is exactly the pattern.

One place it's currently violated in a way worth fixing when convenient: `memberships.role` is a `CHECK` constraint containing `'sub_admin'` and `'student'` — core-layer vocabulary borrowed from the domain. Not urgent, but when the role model is generalised (`ARCHITECTURE.md` §5.1), move role definitions into data rather than a constraint.

---

## 6. Gates before any of this

Do not open a second vertical until all four are true:

1. The campus placement product is genuinely indispensable at 50+ colleges — >85% of drives on-platform, >85% renewal.
2. The Phase 2 network layer exists and works, so the core has been proven to serve more than one product.
3. Demand for the new vertical is **inbound and specific** — a named institution with a budget asking for it, not a market-size estimate.
4. The team is large enough that a second vertical does not slow the first. This is the one that usually isn't true, and it is the one most often ignored.

Until then, this document is a map of terrain you are not walking through yet. The most valuable thing about it is that it tells you which small decisions today — person identity, consent as data, vocabulary discipline — keep the terrain reachable at all.
