# REVERSA — one-page enterprise value proposition

**REVERSA — The Recovery Control Plane for Enterprise AI Operations.**

"AI agents can automate work across systems. REVERSA makes that work
accountable: every action is verified, recoverable failures are safely
compensated, and every outcome carries evidence."

## The problem (priced by the buyer, not by us)

Multi-system workflows partially fail. Each partial failure costs
investigation hours, leaves inconsistent state, and makes the next retry
risky. AI agents multiply workflow volume — and therefore multiply this
failure surface. Current automation answers "what ran"; nobody answers
"what is actually true now, and what was safely undone".

## What REVERSA does (demo-live today)

Policy-controlled execution, verify-after-every-effect, typed
reverse-order compensation, explicit MANUAL_REQUIRED when restoration is
unsafe, and a hash-chained Evidence Passport verifiable offline.

## Build vs buy

| | Hand-rolled saga | Temporal alone | REVERSA |
|---|---|---|---|
| Compensation semantics | you design + test | hand-written per workflow | typed + verified + refused-when-unsafe |
| State reconciliation | you build | retries, your logic | tri-state PRESENT/ABSENT/UNKNOWN |
| Evidence | logs you assemble | event history | offline-verifiable passport |
| AI planning guardrails | you build | n/a | deterministic gate + provenance |

## Objections

- "We already have Temporal." → Keep it. REVERSA is the recovery and
  evidence layer beside it; the pilot instruments one workflow, not a
  migration.
- "Can it undo everything?" → No — and it says so. Irreversible steps
  are flagged pre-execution; unverifiable states escalate, never fake.
- "What does it cost?" → Platform quote + metered inference; the pilot
  measures your reversible share before any annual commitment.
- "Is our data safe?" → Tenant-isolated, secrets server-side, evidence
  exports tenant-scoped; shared view internal-only until the
  commitment-based format ships (stated openly).

## Ask

A 30-day sandbox pilot on ONE failing workflow class, pre-registered
success bar, go/no-go on measured recovery hours (see `pilot-offer.md`).

Customers today: zero. Revenue: zero. Pilots completed: zero. The pilot
is the instrument that changes those numbers — not this page.
