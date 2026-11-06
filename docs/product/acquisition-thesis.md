# Acquisition-readiness thesis — one page (no traction claimed)

Zero LOIs, zero design partners, zero revenue. This thesis states what
would need to be true, not what is.

## Why buy vs build

Typed compensation semantics + tri-state reconciliation + offline-verifiable
evidence took 9 release candidates and 786 tests to harden. An acquirer
buys the recovery contract library, the fault-injection eval corpus, and
the evidence format — not the UI.

## Candidate fit (product-overlap rationale, no contact claimed)

- Temporal / Workato / n8n: add verified recovery + evidence to existing
  orchestration; REVERSA's saga semantics map onto their execution models.
- ServiceNow / Atlassian: audit-grade recovery trail for IT workflows;
  needs enterprise auth/retention work first (roadmap, not built).

## Minimum credible traction (unmet gates)

1. ≥2 signed LOIs from pilot-kit runs. 2. ≥1 paid pilot readout with
buyer-signed S1–S4. 3. One external connector beyond demo scope in
production use. None started; 12–18-month roadmap in commercial docs.

## What is missing today

Buyer-measured recovery data, security audit beyond internal red-team,
multi-tenant production hardening (DB-backed guest sweep), pricing
validation. The hackathon demo proves engineering depth, not a business.
