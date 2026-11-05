# Pilot offer — 30-day Recovery Audit Pilot (REVERSA V2, cycle 2)

- Author: AGENT-18 (Commercial Strategist), 2026-11-05.
- Status: DRAFT proposal. This file is the only file written by AGENT-18
  this cycle. Jury docs (`docs/jury/*`) were NOT edited, per mandate.
- Cycle-3 amendment (2026-11-05, AGENT-18): U7/N1 fix — the
  refused-by-design wording now claims only the code-enforced guard
  (`no_real_payment`); bulk sends / third-party accounts corrected to
  manual/policy-excluded. No numbers changed; ledger §8 still exhaustive.
- Honesty rule (spec §2.3, §15): zero customers, zero revenue, zero
  completed pilots exist or are claimed. Every number below is either
  MEASURED (with source + n) or HYPOTHETICAL (explicitly labeled).
  No dollar figure appears anywhere in this file — pricing is a
  structure hypothesis only, to be earned from pilot data.
- Builds on: `docs/product/commercial-v2.md` §5 (cycle-1 pilot sketch),
  buyer personas P1–P3 defined there; this file is the standalone
  buyer-facing proposal.

## 1. Offer at a glance

- **Name:** Recovery Audit Pilot — "we prove the mess, then we heal it."
- **Duration:** 30 days, fixed scope (proposal term — HYPOTHETICAL until
  a buyer signs it).
- **Where:** buyer's sandbox only, never production first. Chaos/failure
  injection stays locked to non-production tenants, mirroring the
  demo-org lock in the product (`docs/jury/06-security-and-recovery.md`).
- **Shape:** connect ONE real system via the connector SDK (read-first;
  writes only behind plan approval) + keep the remaining steps on
  isolated demo stores. Baseline the buyer's current recovery cost from
  THEIR tickets, then replay THEIR failure shapes and read out against
  a pre-registered bar (§3).
- **Price hypothesis (HYPOTHETICAL, no figure):** fixed-fee pilot,
  credited in full against a year-1 subscription on conversion. The
  figure is set only after buyer interviews — any number printed before
  that would be fiction (`docs/product/commercial-v2.md` §6).
- **Exit:** buyer keeps all evidence exports + the failure-shape report
  even on a "no" (§4). No lock-in story is required to sell the pilot.

## 2. The 30 days (fixed scope)

| Week | Activity | Entry / exit artifact |
|---|---|---|
| 1 — Instrument | Connect ONE real system via SDK (read-first). Writes enabled only behind plan-hash-bound approvals (30-min TTL, implemented behavior per `docs/jury/06`). Baseline current recovery hours/incident + activation/reopen metrics from the buyer's own tickets. | Baseline sheet (buyer's numbers, THEIR source — replaces every HYPOTHETICAL input below). |
| 2–3 — Prove | Replay 3–5 of the buyer's real failure shapes in sandbox (count HYPOTHETICAL scope); per-incident evidence exports delivered to the champion after each run. Failure shapes limited to reversible classes — real-money steps are refused by the enforced `no_real_payment` precondition (`connectors/sdk.py`); bulk sends / third-party-account effects have NO code guard, so they stay out of auto-undo scope (manual / policy-handled). | One evidence export per incident + running readout log. |
| 4 — Decide | Joint readout against the pre-registered success bar (§3). Go / no-go on conversion; either way the buyer keeps §4. | Signed readout: bar met / not met per criterion. |

Guardrails (all implemented product behavior, not promises):

- 15 workflow / 14 action states with allowlisted transitions; DB leases,
  idempotency keys, optimistic versions (`README.md`, Architecture).
- Typed compensation (6 levels); unsafe undo refused with reasons; startup
  reconciliation never blindly retries
  (`docs/product/recovery-proof-engine.md` §0).
- Hash-chained evidence timeline, secrets redacted, offline CLI verify
  (`README.md`); exported `ts` is not hash-covered (stated limit).
- Demo-scale reference point: 10-step onboarding across 5 systems
  (`docs/jury/01-project-overview.md`); happy-path 10/10 COMPLETED,
  execute P50 505 ms (MEASURED, n=10); chaos billing-500 5/5
  COMPENSATED, execute P50 1 783 ms (MEASURED, n=5); chains valid 15/15
  (MEASURED, n=15) — all `docs/benchmarks/results.md`, sequential runs,
  single VM, no concurrency claims.

## 3. Success bar (pre-registered, measurable)

Agreed in writing in week 1; judged in week 4. No criterion may be
edited after week 2 — that is what makes the readout credible.

| # | Criterion | Class |
|---|---|---|
| S1 | ≥50% cut in hands-on recovery time on covered failure shapes, measured buyer-before vs. pilot-after from the week-1 baseline. | HYPOTHETICAL bar (threshold to validate; the MEASURED delta replaces it at readout). |
| S2 | 100% of pilot incidents ship with a valid evidence chain (API verdict; CLI spot-check), mirroring the measured 15/15 demo discipline (MEASURED, n=15, `docs/benchmarks/results.md`). | MEASURED discipline, applied to pilot scope. |
| S3 | Zero unapproved writes outside approved plans (approval = plan-hash-bound, 30-min TTL, `docs/jury/06`). | Pass/fail count from evidence (MEASURED at readout, n = pilot runs). |
| S4 | Every irreversible/manual step in pilot scope surfaces as an enumerated manual item with a reason — none silently retried or auto-undone (engine behavior, `docs/product/recovery-proof-engine.md` §0). | Pass/fail from manifests (MEASURED at readout). |

Illustrative inputs the baseline REPLACES (do not pitch as facts):
2–6 h senior-IT cleanup per failure, 50 onboardings/month, 10% failure
rate (all HYPOTHETICAL per `docs/product/commercial-v2.md` §1 audit B2–B3).
The pilot exists to swap these for the buyer's measured numbers.

## 4. What the buyer keeps (either outcome)

- All per-incident evidence exports (JSON/HTML) + offline-verify CLI
  instructions — auditor-readable incident records with zero manual work.
- The failure-shape report: which of their shapes are reversible,
  conditionally reversible, or refused-by-design, with the evidence
  pointer per shape.
- The week-1 baseline sheet and the week-4 readout (bar met / not met
  per criterion) — usable in their own QBRs and vendor comparisons.
- No data held hostage: single-VM Compose footprint runs in their
  sandbox; nothing phones home (see honest limits, §7).

## 5. Tier hypotheses (structure only — no prices)

HYPOTHETICAL packaging to validate in buyer interviews. Axes follow the
`docs/jury/08-business-case.md` sketch and `docs/product/commercial-v2.md`
§6. Explicitly NOT set: dollar figures, seat-vs.-usage mix, SLA terms.

| Tier (HYPOTHETICAL name) | Hypothesized fit | Hypothesized differentiators |
|---|---|---|
| Developer / Community | Evaluators, OSS footprint | Self-host, demo connectors + SDK, community support, shortest history retention. |
| Team | One team, one org (P1 champion's team) | More organizations/executions, longer retention, first real connectors, standard support. |
| Business | Multi-team SaaS / RevOps (P1 + P2) | More connectors, longer retention, SSO, activation-SLA reporting (§6 P2 metrics). |
| Enterprise | Regulated / MSP fleets (P3) | Longest retention, SSO + audit exports at scale, fleet/multi-org, premium support. |

Pricing principles (hypotheses, not terms):

- Platform fee + execution volume; overage on evidence retention, never
  on compensation runs — never tax the healing.
- The pilot credit (§1) is the only discount mechanism hypothesized;
  no other discount or tier-price number exists in this proposal.

## 6. Buyer-persona messaging

Personas P1–P3 per `docs/product/commercial-v2.md` §3 (spec §2.3 buyer
list). Each block: headline → grounded proof → objection → pilot CTA.
Anti-personas (no automation yet; 500-connector day-one demand;
real-time/high-throughput) per commercial-v2 §3 — do not pitch them.

### P1 — Head of Business Systems (primary champion)

- **Headline:** "Your next 3 a.m. provisioning page comes with its own
  incident report — and the mess already undone."
- **Proof (all repo-grounded):** (1) billing-500-class failure detected,
  dependents blocked, reverse-order compensation, restoration verified —
  5/5 COMPENSATED (MEASURED, n=5, `docs/benchmarks/results.md`); (2)
  every run sealed in a hash-chained Evidence Passport with offline CLI
  verify (`README.md`); (3) REVERSA never silently retries — startup
  reconciliation never blindly retries, unsafe undo is refused with
  reasons (`docs/product/recovery-proof-engine.md` §0).
- **Objection:** "Another platform to babysit." **Answer:** read-only
  evidence + refusal-by-design; real-money steps are refused by an
  enforced precondition (`no_real_payment`, `connectors/sdk.py`), and
  anything it cannot safely undo surfaces as a manual item with a
  reason instead of failing quietly at 3 a.m. Bulk sends and
  third-party-account effects have no code guard yet — the pilot keeps
  them manual and out of auto-undo scope.
- **Pilot CTA:** "Give us one sandbox system and your five ugliest
  recent provisioning tickets. In 30 days you get the baseline, the
  replays, and the evidence exports — yours to keep even if you pass."
- **Their win at readout:** recovery hours/incident (S1), % incidents
  with complete evidence (S2), zero unapproved writes (S3) — mapped to
  the support-ticket tags they already track.

### P2 — Head of RevOps (economic buyer for the wedge)

- **Headline:** "Every closed-won deal either activates verified — or
  fails loudly with proof, never half-provisioned in silence."
- **Proof:** (1) activation as a verified workflow: every effect
  re-checked, UNKNOWN→verify→idempotent-retry reconciliation instead of
  blind re-runs (engine behavior, `docs/product/competition.md` matrix);
  (2) failed activations compensated in reverse order with verified
  absence, not left half-provisioned (demo behavior, `docs/jury/04`
  per commercial-v2 §1.3); (3) per-deal ops timeline (Evidence Passport)
  ready for QBRs.
- **Objection:** "Salesforce already does this." **Answer:** Salesforce
  orchestrates records, not cross-system undo with verification.
  REVERSA is the control layer above it — different layer, proven on
  the 10-step / 5-system onboarding shape (`docs/jury/01`).
- **Pilot CTA:** "Pick the activation path with the worst
  closed-won-to-live gap. We baseline it in week 1 and you judge us on
  activation SLA attainment in week 4."
- **Their win at readout:** closed-won-to-live days, duplicate-resource
  incidents, manual reconciliation hours/week (UC3 metrics,
  commercial-v2 §4) — all buyer-measured, none pre-claimed.

### P3 — CTO / VP Engineering, incl. MSP variant (technical approver)

- **Headline:** "Typed, tested compensation instead of bespoke rollback
  code — on infrastructure you can read in one sitting."
- **Proof:** (1) 15 workflow / 14 action states, allowlisted
  transitions, leases, idempotency, crash reconciliation (`README.md`);
  (2) 6 reversibility levels with verify-after-compensate and terminal
  distinction COMPENSATED vs PARTIALLY_COMPENSATED vs MANUAL_REQUIRED
  (recovery-proof-engine §0); (3) one VM + Compose today, deterministic
  planner fallback when no inference key, measured sequential numbers
  with explicit NOT-claimed concurrency limits
  (`docs/benchmarks/results.md`).
- **Objection:** "We'll build it on Temporal." **Answer:** Temporal
  gives durable execution; REVERSA adds verify-after-every-effect,
  refuse-when-unsafe compensation, and hash-chained evidence out of the
  box. The 30-day pilot IS the build-vs-buy test — fixed scope, kept
  artifacts, pre-registered bar.
- **Pilot CTA (MSP variant):** "Run it against your costliest customer
  onboarding playbook. Judge us on on-call hours per customer onboarded
  and MTTR on provisioning incidents."
- **Their win at readout:** S1–S4 (§3) plus the refusal catalog — every
  refused undo with its reason, auditable in the evidence chain.

## 7. Honest limits (part of the pitch, not the fine print)

- Zero customers, zero revenue, zero completed pilots — stated openly;
  this proposal is HYPOTHETICAL until a buyer signs it.
- Connector breadth honestly Behind: 6 demo connectors + SDK today
  (`docs/product/competition.md`); the pilot's "1 real connector" via
  SDK is the scope limiter, and the GitHub test-repo connector
  (`docs/product/github-connector.md`) is the first real-connector path.
- No scale story: sequential worker, measured campaigns only (n=10
  happy, n=5 chaos); load campaigns 25/50/100 NOT run
  (`docs/benchmarks/results.md` "NOT claimed").
- No exactly-once claim on external systems; the hash chain detects
  tampering but is not absolute immutability alone; exported `ts` is
  not hash-covered (`README.md`).
- Refusal-guard status, stated plainly: only `no_real_payment` is a
  code-enforced precondition (`connectors/sdk.py`); bulk sends and
  third-party-account effects have no guard in code, so the pilot
  scopes them as manual — never auto-undone, never claimed otherwise.
- Internal self-scores (e.g. Business value 7,
  `docs/product/competition.md`) are never pitched as official ratings.

## 8. Number ledger (every number in this file)

| # | Figure | Class | Source |
|---|---|---|---|
| N1 | 30 days, 1 real system, weeks 1/2–3/4 | Proposal terms (HYPOTHETICAL until signed) | This file §1–§2 |
| N2 | 3–5 failure shapes | HYPOTHETICAL scope | This file §2 |
| N3 | ≥50% cut (S1) | HYPOTHETICAL bar | This file §3; replaced by MEASURED delta at readout |
| N4 | 5 systems, 10 steps | Demo scope (implemented) | `docs/jury/01` |
| N5 | 10/10 COMPLETED, P50 505 ms | MEASURED (n=10) | `docs/benchmarks/results.md` |
| N6 | 5/5 COMPENSATED, P50 1 783 ms | MEASURED (n=5) | `docs/benchmarks/results.md` |
| N7 | Chains valid 15/15 | MEASURED (n=15) | `docs/benchmarks/results.md` |
| N8 | 30-min approval TTL | Implemented behavior | `docs/jury/06` |
| N9 | 15 wf / 14 action states, 6 capabilities | Implemented | `README.md`, recovery-proof-engine §0 |
| N10 | 2–6 h, 50/month, 10% | HYPOTHETICAL (replaced by buyer baseline) | commercial-v2 §1 audit B2–B3 |
| N11 | Tier names, axes, credit mechanism | HYPOTHETICAL (no figures) | This file §1, §5; sketch in `docs/jury/08` |
| N12 | 6 demo connectors + SDK | Stated inventory | `docs/product/competition.md` |
| N13 | Zero customers / revenue / pilots | Stated non-claim | Spec §2.3; this file §7 |
