# Commercial v2 — Business case strengthening (REVERSA V2, cycle 1)

- Author: AGENT-18 (Commercial Strategist), 2026-11-05.
- Status: DRAFT proposal. This file is the only file written by AGENT-18.
- Jury docs (`docs/jury/*`) were NOT edited this cycle, per mandate.
- Cycle-3 amendment (2026-11-05, AGENT-18): U7 fix in UC1 limits +
  §8 recommendation status check. No numbers changed.
- Honesty rule (spec §2.3, §15): no revenue, customers, or real ROI exist or
  are claimed. Every number below is either MEASURED (with source) or
  HYPOTHETICAL (explicitly labeled, buyer-editable).

## 1. Number audit — `docs/jury/08-business-case.md` + `/roi` page

Scope: every numeric claim in the business case and the ROI calculator.
Verdict scale: MEASURED (reproducible source) / HYPOTHETICAL (illustrative,
must stay editable and labeled) / FIX (wording change proposed for cycle 2).

### 1.1 Business case (`docs/jury/08-business-case.md`)

| # | Claim (as written) | Class | Source / justification | Action |
|---|---|---|---|---|
| B1 | "onboarding touches 4–8 systems" | HYPOTHETICAL | Illustrative range; demo uses 5 systems (`docs/jury/01`, `04`). No market study behind 4–8. | Keep as hypothesis; prefix "typically, in our target segment (to validate)". |
| B2 | "a failed run costs 2–6 hours of senior IT time" | HYPOTHETICAL | Illustrative range, no source. | Keep; add "hypothesis — pilot measures this". |
| B3 | "At 50 onboardings/month and a 10% failure rate, that is 10–30 h/month" | HYPOTHETICAL (arithmetically correct) | 50 × 10% = 5 incidents × 2–6 h = 10–30 h. Math checks out; inputs are hypotheses. | Keep; label inputs explicitly hypothetical in text. |
| B4 | "200–2000-person SaaS" (first buyers) | HYPOTHETICAL | Segment hypothesis, no validation data. Consistent with spec §2.3 (IT Ops, RevOps, SaaS, MSPs). | Keep; personas in §3 sharpen it. |
| B5 | "100% demo recovery rate as default" | MEASURED (narrow scope) | `docs/benchmarks/results.md` (2026-11-05): 5/5 chaos billing-500 runs → COMPENSATED, sequential, demo stores. | Keep wording "measured demo-benchmark rate (n=5)"; never shorten to "100% recovery" without the qualifier. |
| B6 | "No pricing is final; no revenue, customers, or ROI are claimed" | COMPLIANT | Explicit non-claim, matches spec §2.3. | Keep verbatim. |

### 1.2 ROI page (`reversa/apps/web/app/roi/page.tsx`)

| # | Default value | Class | Source / justification | Action |
|---|---|---|---|---|
| R1 | workflows = 50/month | HYPOTHETICAL | Matches B3; user-editable. | OK — page already says "Hypotheses you can edit". |
| R2 | failure rate = 10% | HYPOTHETICAL | Matches B3; user-editable. | OK. |
| R3 | recovery cost = $150/incident | HYPOTHETICAL | No source; plausible senior-IT loaded cost per 2–6 h is actually *higher* — $150 is conservative, but still unsourced. | OK as editable default; propose adding "(edit me — your loaded cost)" hint in cycle 2. |
| R4 | recovery time = 4 h/incident | HYPOTHETICAL | Midpoint of B2's 2–6 h range. Consistent. | OK. |
| R5 | auto-compensated share = 100% | MEASURED default, HYPOTHETICAL as buyer projection | Source: chaos campaign 5/5 (n=5, demo). Correctly labeled on-page with pointer to `docs/benchmarks`. | OK — best-labeled number on the page. Do not dilute the qualifier. |
| R6 | Formulas (incidents, saved, hours) | CORRECT | incidents = workflows × rate; saved = incidents × auto-share × cost. Linear, no compounding tricks. | OK. |
| R7 | "No invented customers or savings" | COMPLIANT | Explicit non-claim on-page. | Keep. |

### 1.3 Numbers this file reuses (all sourced or labeled)

- Demo scale: 5 systems, 10 steps, 10-step onboarding — `docs/jury/01`.
- Chaos result: 5/5 COMPENSATED, execute P50 1 783 ms — `docs/benchmarks/results.md`.
- Happy-path: 10/10 COMPLETED, execute P50 505 ms — same source.
- Evidence: 59-event chain per happy run — `docs/jury/04`; chains valid 15/15
  (2026-11-05) — `docs/benchmarks/results.md`.
- Internal self-scores (e.g. Business value 7) — `docs/product/competition.md`
  (AGENT-17/20 self-assessment, never presented as official).
- Everything else (market sizes, deal sizes, conversion, headcount, revenue,
  timelines for hiring/funding) is HYPOTHETICAL and labeled as such.

## 2. Positioning (unchanged thesis, sharper wording)

- **Problem (buyable, spec §2.3):** teams that already automate
  (Zapier/n8n/Temporal) eat the recovery cost when multi-system runs fail
  halfway: senior-IT cleanup hours, customer-facing delay, churned trials.
- **Wedge:** the control layer for operations that must be *undone* safely —
  typed compensation + reconciliation + hash-chained evidence in one platform,
  with AI planning constrained by policy.
- **What we are not (honest limits):** not a 500-connector platform (6 demo
  connectors + SDK today, per `docs/product/competition.md`); not a scale
  story (one VM, sequential runs, measured); not a validated business (zero
  customers, zero revenue — stated openly).

## 3. Buyer personas (strengthened)

Derived from spec §2.3 buyer list (CTO, VP Engineering, Head of IT, Head of
RevOps, Head of Business Systems) and priority markets (IT Ops, RevOps, SaaS,
automation platforms, MSPs, support/onboarding).

### P1 — Head of Business Systems (primary champion)

- **Owns:** the Zapier/n8n/Salesforce glue at a 200–2000-person SaaS.
  (Size band HYPOTHETICAL.)
- **Pain:** 3 a.m. pages when onboarding half-provisions a customer; no record
  of what was undone; audit asks "prove it" and the answer is screenshots.
- **Jobs-to-be-done:** (1) cut reactive cleanup hours; (2) produce an
  auditor-readable incident record without manual work; (3) say "no" safely to
  un-undoable automations.
- **Success metric they already track:** support tickets tagged
  provisioning/onboarding; time-to-resolve. Pilot maps to these (§5).
- **Objection:** "Another platform to babysit." Answer: read-only evidence +
  refusal-by-design; REVERSA never silently retries (startup reconciliation
  never blindly retries — engine behavior, `docs/product/recovery-proof-engine.md` §0).

### P2 — Head of RevOps (economic buyer for the wedge)

- **Owns:** CRM → contract → provisioning activation chain; forecast accuracy.
- **Pain:** deals marked "closed-won" that stall in provisioning; RevOps
  manually reconciles CRM vs. billing vs. entitlements.
- **Jobs-to-be-done:** (1) every activation verified cross-system; (2) failed
  activations compensated, not left half-provisioned; (3) a per-deal ops
  timeline for QBRs.
- **Success metric:** activation SLA attainment; days from closed-won to live.
- **Objection:** "Salesforce already does this." Answer: Salesforce orchestrates
  records, not cross-system undo with verification. Different layer.

### P3 — CTO / VP Engineering (technical approver, MSP variant)

- **Owns:** platform reliability; for MSPs, margin on managed onboarding/support.
- **Pain:** hand-written sagas in Temporal (or worse, none); each new system
  multiplies untested error paths; on-call toil grows with customer count.
- **Jobs-to-be-done:** (1) typed, tested compensation instead of bespoke
  rollback code; (2) deterministic, reproducible failure handling they can demo
  to *their* customers; (3) self-hostable footprint (one VM + Compose today).
- **Success metric:** on-call hours per customer onboarded; MTTR on
  provisioning incidents.
- **Objection:** "We'll build it on Temporal." Answer: Temporal gives durable
  execution; REVERSA adds verify-after-every-effect, refuse-when-unsafe
  compensation, and hash-chained evidence out of the box. Build-vs-buy pilot
  settles it in 30 days (§5).

### Anti-personas (who NOT to sell to in year 1)

- Teams with no automation yet (nothing to heal — sell them Zapier first).
- Enterprises requiring 500+ native connectors on day one (we are Behind on
  breadth, honestly — `docs/product/competition.md`).
- Real-time / high-throughput workloads (sequential worker by design; no
  concurrency claims — `docs/benchmarks/results.md` "NOT claimed").

## 4. Use cases (spec §15.1 — three credible scenarios)

All gains HYPOTHETICAL unless they cite a measured demo behavior.

### UC1 — SaaS enterprise onboarding (flagship; = the live demo)

- **Problem:** provisioning spans CRM, identity, workspace, support, billing;
  a mid-run failure leaves ghost accounts and inconsistent entitlements.
- **Current workflow:** n8n/Zapier happy-path automation + manual cleanup when
  it breaks; evidence = chat logs.
- **Consequences:** 2–6 h senior-IT cleanup per failure (HYPOTHETICAL, B2);
  delayed go-live; trial churn (unquantified — do not quantify without data).
- **REVERSA approach:** 10-step verified plan; billing-500-class failures
  detected, compensated in reverse order, restoration verified, 59-event
  evidence chain exported (demo behavior, `docs/jury/04`).
- **Potential gains (HYPOTHETICAL):** recovery hours → near-zero on
  reversible failures; every incident ships with an auditor-readable report.
- **Limits:** demo connectors, not the buyer's real stack; real-money steps
  are refused by the enforced `no_real_payment` precondition
  (`connectors/sdk.py`), and IRREVERSIBLE / MANUAL_ONLY steps stay manual
  with reasons. Bulk sends have no code guard yet — pilot scope treats
  them as manual/policy-excluded, never auto-undone.
- **Measurable metrics:** recovery hours/incident; % incidents with complete
  evidence export; activation SLA attainment.

### UC2 — Customer support operations

- **Problem:** resolving one incident touches support queue, CRM, identity,
  billing (credits), and notification systems; partial fixes contradict each other.
- **Current workflow:** swivel-chair across 4–8 consoles (HYPOTHETICAL count);
  no cross-system consistency check.
- **Consequences:** reopened tickets; contradictory customer comms; credits
  issued without record linkage.
- **REVERSA approach:** one verified run per resolution playbook; precondition
  checks block stale-version writes; compensation order proven in reverse.
- **Potential gains (HYPOTHETICAL):** fewer reopened tickets; every credit tied
  to its evidence chain.
- **Limits:** playbooks must be modeled as plans first; human-approval steps
  (plan hash + 30-min TTL, `docs/jury/06`) add latency by design.
- **Measurable metrics:** ticket reopen rate; mean time to verified resolution;
  % credit actions with linked evidence.

### UC3 — Revenue operations (CRM → contract → activation)

- **Problem:** closed-won deals stall between CRM, contract, and provisioning;
  nobody owns the cross-system state.
- **Current workflow:** RevOps exports, eyeballs diffs, nudges owners.
- **Consequences:** slipped go-lives; forecast vs. reality gaps; manual
  reconciliation toil (unquantified).
- **REVERSA approach:** activation as a verified workflow with
  UNKNOWN→verify→idempotent-retry reconciliation instead of blind re-runs
  (engine behavior, `docs/product/competition.md` matrix).
- **Potential gains (HYPOTHETICAL):** days from closed-won to live;
  zero duplicate-provisioning incidents.
- **Limits:** requires connector(s) to the buyer's CRM/billing — the "1 real
  connector" gap (`docs/product/competition.md`) must close first.
- **Measurable metrics:** closed-won-to-live days; duplicate-resource incidents;
  manual reconciliation hours/week.

## 5. Pilot offer (concrete, measurable, honest)

> HYPOTHETICAL commercial proposal — no pilot has run. Figures are opening
> positions to validate in buyer interviews, not validated pricing.

- **Name:** Recovery Audit Pilot ("we prove the mess, then we heal it").
- **Duration:** 30 days, fixed scope, in the buyer's sandbox (never production
  first — chaos stays demo-org-locked per `docs/jury/06`).
- **Week 1 — Instrument:** connect ONE real system via SDK (read-first; write
  only behind plan approval) + keep demo stores for the rest. Baseline the
  buyer's current recovery hours/incident from their tickets.
- **Weeks 2–3 — Prove:** replay 3–5 of the buyer's real failure shapes in
  sandbox; ship per-incident evidence exports to the champion.
- **Week 4 — Decide:** joint readout against the pre-registered success bar:
  (a) ≥50% cut in hands-on recovery time on covered failure shapes
  (HYPOTHETICAL bar); (b) 100% of pilot incidents with valid evidence chains
  (mirrors the measured 15/15 demo discipline); (c) zero unapproved writes.
- **Price hypothesis (HYPOTHETICAL):** fixed-fee pilot credited against year-1
  subscription on conversion; Team/Business/Enterprise tiers differentiate on
  history retention, connectors, SSO, support (per `docs/jury/08` sketch).
- **Exit:** buyer keeps all evidence exports + the failure-shape report even on
  a "no". No lock-in story is required to sell the pilot.

## 6. SaaS model sketch (spec §15.2 — hypotheses to validate)

- **Tiers:** Developer/Community (self-host, demo connectors, community
  support) → Team → Business → Enterprise. Axes: organizations, executions,
  history retention, connectors, SSO, support.
- **Billing hypotheses (HYPOTHETICAL):** per-organization platform fee +
  execution volume; overage on evidence retention, not on compensation runs
  (never tax the healing — pricing principle).
- **Explicitly NOT set:** dollar figures, seat vs. usage mix, SLA terms. Any
  number here before buyer interviews would be fiction; §5's pilot exists to
  earn the first real numbers.

## 7. Twelve-month roadmap (HYPOTHETICAL plan, evidence-gated)

Gates are honest: each phase's exit criterion is a measured artifact, and
phases do not start until the gate clears. Dates assume a post-hackathon team;
no headcount or funding is claimed.

| Quarter | Theme | Ship (hypothetical scope) | Exit gate (measured) |
|---|---|---|---|
| Q1 | Prove it on real systems | 1 real connector (GitHub test connector first, per `docs/product/competition.md` gap); rate limits + CSRF audit; load campaigns 25/50/100 wf | Real-connector chaos run COMPENSATED with valid chain; published bench numbers replacing "sequential only" |
| Q2 | Earn the first pilots | Recovery Audit Pilot kit (§5): sandbox installer, baseline template, readout template; 5–10 buyer interviews (HYPOTHETICAL count) | 2 design-partner LOIs signed; interview notes converted into priced requirements |
| Q3 | Harden the trust story | Vultr inference key live with published eval (AI score 6→8 path, `docs/product/competition.md`); manifest/RPE implementation if V2 spec approved; fresh-install video | Eval published; 10-case injection/forbidden-delete suite green on the live key |
| Q4 | Convert or learn | Paid pilots against the §5 success bar; pricing v1 from pilot data; SOC2-readiness checklist started (checklist only — no certification claim) | ≥1 paid pilot readout with measured recovery-hour delta; every commercial number in this file either re-sourced or re-labeled |

## 8. Cycle-2 recommendations (for the jury-docs owner, NOT applied here)

1. 08-business-case.md B1–B3: add one line — "All figures in this paragraph
   are hypotheses; edit them live on /roi." (Closes the only labeling gap found.)
2. `/roi` R3: append "(edit me — your loaded cost)" to the cost label.
3. Never compress B5/R5's "measured demo-benchmark rate (n=5)" into a bare
   "100%" in slides or pitch; the qualifier is the credibility.
4. Keep the internal 10/10 grid (`docs/product/competition.md`) out of jury
   materials; it is self-assessment, and presenting it invites exactly the
   wrong question.

Cycle-3 status check (2026-11-05, AGENT-18 — file owner; jury docs
still NOT edited, per mandate):

- Rec 1: OPEN — `docs/jury/08-business-case.md:3-6` still carries B1–B3
  unlabeled; the one-line hypothesis label is still the fix.
- Rec 2: OPEN — `reversa/apps/web/app/roi/page.tsx:34` cost label
  unchanged; "(edit me — your loaded cost)" hint still missing.
- Rec 3: HOLDING on `/roi` (qualified labels intact,
  `page.tsx:36-37,53-55`); EXTEND to `docs/jury/08:24`, whose
  "measured 100% demo recovery rate" still lacks the "(n=5)" qualifier.
- Rec 4: HOLDING — no self-assessment grid in jury materials, only the
  pointer at `docs/jury/08:11`. Keep it that way.
- Rec 5 (NEW): narrow the U7 overstatement in
  `docs/jury/06-security-and-recovery.md:22-23` — only `no_real_payment`
  is code-enforced (`connectors/sdk.py:145-147`); bulk sends /
  third-party-account effects have no guard. Commercial files fixed this
  cycle (`pilot-offer.md` §2 table + P1 block + §7; this file UC1).
