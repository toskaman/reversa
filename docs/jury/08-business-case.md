# 08 — Business case (hypotheses, not customers)

**Problem (priced — all figures hypotheses, to validate):** mid-market
SaaS onboarding typically touches 4–8 systems; a failed run costs 2–6 hours
of senior IT time plus customer-facing delay. At 50 onboardings/month and a
10% failure rate, that is 10–30 h/month of reactive cleanup — before counting
churned trials. Edit every input live on `/roi`; the pilot replaces them
with the buyer's measured numbers.

**REVERSA's wedge:** teams that already automate (Zapier/n8n/Temporal) but
eat the recovery cost. Differentiators vs. each: typed compensation +
reconciliation + evidence in one platform, with AI planning constrained by
policy (see competitor matrix in working notes).

**First buyers:** Head of IT / RevOps / Business Systems at 200–2000-person
SaaS and MSPs running customer onboarding and support operations.

**Model sketch (to validate):** per-organization platform fee + execution
volume; Team/Business/Enterprise tiers by history retention, connectors, SSO
and support. No pricing is final; no revenue, customers, or ROI are claimed.

**Land motion:** 1-click Jury Mode launch (guest session → plan → approve
→ execute, owner token only as fallback) → connect one real system in a
sandbox → paid pilot measured on recovery hours saved.

**Measured proof behind the pitch (RC9 v0.2.0-rc.9 + V8):** 787-test API suite
green (1 xfailed pinned SSE leak, 2 honest skips), chaos matrix 20/20, 100-case offline planner eval
plus live Vultr Inference campaigns (2×10 + 12-case A/B, 65,553 tokens,
in-repo aggregates) — baseline 100% schema-valid, 0% refusal, a stated
limitation.

**Interactive calculator:** the live `/roi` page implements §15.3 with
editable hypotheses and the measured demo recovery rate (100%, n=5 chaos
runs) as default.
