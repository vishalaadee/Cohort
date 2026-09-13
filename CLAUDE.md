# Working on Cohort — read this first

**Before making any architectural or product decision, read [`docs/PRODUCT_VISION.md`](docs/PRODUCT_VISION.md) in full.** It's the founder's north star for this project and explains context that the code alone won't give you: what this product is trying to become, why, and — just as importantly — what *not* to build yet.

## The one-paragraph version

Cohort is Phase 1 of a multi-tenant *network* (not just multi-tenant SaaS) for Indian college placements: replace the Google Forms/WhatsApp/spreadsheet chaos with one real platform for Tier‑2/Tier‑3 colleges, run by Placement Officers with CRs as scoped assistants, never as co-authorities. Phase 2 (a cross-college student–employer talent network, common assessments, longitudinal profiles) comes later and is out of scope until Phase 1 has real adoption — but the identity, tenancy, permission, student-profile, and audit foundations should be built so Phase 2 doesn't require ripping them out.

## Non-negotiables

- **Tenant isolation is never sacrificed for convenience.** Every query is tenant-scoped; see `docs/BACKEND.md` for how RLS enforces this today.
- **Backend authorization is authoritative.** Never rely on the frontend to hide something that isn't actually permission-checked server-side.
- **Authority hierarchy:** Placement Officer / College Admin → CR → Students. CRs get configurable, scoped permissions per college, but must never become equivalent to the Placement Officer.
- **Don't build Phase 2 now** (talent marketplace, cross-college discovery, employer subscriptions, common assessments as a shipped product) unless a Phase 1 decision would make it needlessly hard later — in which case, flag it rather than quietly building it.
- **Investigate before you claim.** Never say something exists (or doesn't) in the codebase without actually opening and reading it. Existing changes may be work-in-progress — check the real diff/migrations before extending them.
- **Explain before risky changes.** For significant or irreversible changes, propose the approach first. Keep commits coherent and reviewable. Never deploy to production or touch shared infrastructure destructively without explicit approval.

## Repo orientation

See the root [`README.md`](README.md) for the repo layout, and `docs/BACKEND.md`, `docs/FRONTEND.md`, `docs/INFRA.md`, `docs/USAGE.md` for the how. `docs/PRODUCT_VISION.md` is the why — read it first.
