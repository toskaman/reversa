# 13 — 30-question adversarial gauntlet (V6, RC8)

Each item: Vulnerability / Hardened Fix (with repo paths) /
Ten-Second Rebuttal + Severity, Evidence, Missing proof, Owner,
Priority, Status. No hand-waving: every fix is a task, a shipped
change, or a documented limitation.

Conventions: severity P0 (blocks submission) / P1 (fix pre-judging
if cheap) / P2 (post-hackathon). Status DONE / OPEN / ACCEPTED /
WONTFIX.

## Cluster 1 — VC / product judge

### Q1. Why isn't REVERSA a feature ServiceNow/Workato/Temporal ships fast?

- Vulnerability: incumbents own distribution; saga/retries exist.
- Fix: differentiate on what is DEMONSTRATED, not claimed:
  typed verified compensation + verify-after-undo + refusal to
  claim recovery + offline-verifiable Evidence Passport
  (`docs/product/competition-v2.md`, `reversa/apps/api/src/
  reversa_api/engine/`, `routes/recovery.py`). No code change.
- Rebuttal: "They can copy the UI; the moat is the recovery
  contract suite — 20/20 chaos scenarios re-runnable today."
- P2 · Evidence: chaos matrix green, competition matrix ·
  Missing: head-to-head pilot · Owner: 17 · Status: ACCEPTED.

### Q2. Who has budget authority, and which expense does it replace?

- Vulnerability: no buyer = no revenue.
- Fix: buyer wedge documented — Head of IT/RevOps/Business
  Systems at 200–2000-person SaaS + MSPs; replaces manual
  recovery hours (`docs/jury/08-business-case.md:10-24`).
- Rebuttal: "The buyer already pays engineers to clean up
  half-failed automations — we meter that cost away."
- P2 · Evidence: business case + ROI simulator (hypotheses
  labeled) · Missing: first pilot $ · Owner: 17 ·
  Status: ACCEPTED.

### Q3. Gross margin at realistic inference/storage/support cost?

- Vulnerability: LLM + storage + support could erase margin.
- Fix: unit-economics model with MEASURED vs ASSUMED split
  (`08-business-case.md` ROI; live tokens 65,553 measured;
  VM $0.28 observed). No invented MRR.
- Rebuttal: "Inference is cents per workflow on flash models;
  evidence storage is append-only rows — margin modeled, not
  wished."
- P2 · Evidence: token + spend Ledger · Missing: at-scale
  support cost · Owner: 16 · Status: ACCEPTED.

### Q4. First 1,000 users without a marketing budget?

- Vulnerability: distribution from zero.
- Fix: 1-click public demo + reproducible repo + Vultr
  Community post (optional, post-submission). Honest: no
  growth hack claimed.
- Rebuttal: "The demo IS the funnel: launch, break, watch it
  heal — then clone the repo."
- P2 · Evidence: Jury Mode, fresh-clone PASS · Missing:
  launch metrics · Owner: 19 · Status: ACCEPTED.

### Q5. Why keep paying after the first successful recovery?

- Vulnerability: one-shot value perception.
- Fix: position as control plane, not incident tool: every
  workflow carries policy, approval, evidence, retention
  (`08-business-case.md` Team/Business/Enterprise tiers).
- Rebuttal: "You don't cancel the audit trail after the
  first audit."
- P2 · Evidence: tiered packaging draft · Missing: retention
  data · Owner: 17 · Status: ACCEPTED.

### Q6. What if an incumbent copies our interface and demo?

- Vulnerability: UI is copyable in days.
- Fix: nothing to fix in UI; defensibility = compensation
  semantics + fault-injection evals + evidence provenance
  (all in-repo, timestamped commits). Strategy A selected
  over B/C on evidence (V6 sweep).
- Rebuttal: "Copy the pixels — you still have to survive
  our 20-scenario chaos matrix in public."
- P2 · Evidence: dated git history, eval harness · Missing:
  none · Owner: 17 · Status: DONE.

### Q7. What keeps the product alive right after the hackathon?

- Vulnerability: demo-rot.
- Fix: Horizon-1 plan (stabilize deploy, SDK-ify connectors,
  recruit pilots) + RC process that already ships weekly
  (`CHANGELOG.md` RC1→RC8).
- Rebuttal: "Eight release candidates in four days — this
  team ships."
- P2 · Evidence: CHANGELOG, CI history · Missing: post-event
  calendar · Owner: 01 · Status: ACCEPTED.

## Cluster 2 — AI/ML architect

### Q8. Integrity during financial/mission-critical ops; impossible guarantees?

- Vulnerability: over-claiming safety.
- Fix: policy gate is deterministic, NOT the LLM
  (`planner/validate.py`); real payments refused by missing
  capability; docs state no exactly-once on external systems.
- Rebuttal: "AI proposes, policy decides — and we publish
  what we CANNOT guarantee."
- P1 · Evidence: refusal paths tested, honest-limits README
  section · Missing: external pentest · Owner: 03 ·
  Status: DONE.

### Q9. Why an LLM where deterministic code is faster and safer?

- Vulnerability: LLM theater.
- Fix: measured split — deterministic baseline is the
  default; Vultr Inference handles open-ended intents the
  template cannot (A/B + 2×10 evals, provenance shown in
  UI). Never an LLM-only path.
- Rebuttal: "Templates run the known; the model earns the
  unknown — with receipts."
- P1 · Evidence: `05-ai-integration.md` A/B record · Missing:
  larger-n evals · Owner: 05 · Status: ACCEPTED.

### Q10. Responsive latency despite inference + multi-step execution?

- Vulnerability: slow-feeling demo.
- Fix: streaming SSE timeline + P50 measured (plan ~1.9 s,
  onboarding 505 ms exec baseline); no fake progress bars.
- Rebuttal: "Live event stream from step one — perceived
  latency is visibility."
- P1 · Evidence: `docs/benchmarks/results.md` · Missing:
  P95 at N≥25 · Owner: 11 · Status: ACCEPTED.

### Q11. Benchmark of AI DECISION quality beyond valid JSON?

- Vulnerability: schema-valid ≠ correct.
- Fix: decision evals (PLAN/CLARIFY/REFUSE) with per-case
  verdicts, not just JSON validity (V5 eval harness, A/B
  12 cases with named failures).
- Rebuttal: "We grade decisions, and we publish the ones
  the model got wrong."
- P1 · Evidence: eval reports in repo · Missing: n≥100 live
  (cost) · Owner: 05 · Status: ACCEPTED.

### Q12. Defense vs prompt injection, poisoned input, provider failure?

- Vulnerability: classic LLM attack surface.
- Fix: injection cases in evals; validator rejects unknown
  capabilities regardless of prompt; provider outage →
  explicit deterministic fallback with provenance (tested).
- Rebuttal: "Inject all you want — the gate only speaks
  registered capabilities."
- P1 · Evidence: injection eval cases, fallback tests ·
  Missing: third-party red-team · Owner: 08 · Status: DONE.

### Q13. Upstream model behavior change?

- Vulnerability: silent drift.
- Fix: model pinned by name in config + provenance recorded
  per plan; evals re-runnable on demand; validator blocks
  drift-induced invalid plans automatically.
- Rebuttal: "Pinned model, recorded provenance, re-runnable
  evals — drift gets caught, not shipped."
- P2 · Evidence: provenance fields, eval harness · Missing:
  scheduled drift monitor · Owner: 03 · Status: ACCEPTED.

### Q14. Why Vultr Inference over a local SLM or pure templates?

- Vulnerability: sponsor-tech checkbox.
- Fix: genuine use — managed flash models, no GPU ops,
  measured cost/latency; templates remain for offline +
  fallback (fresh-clone works keyless).
- Rebuttal: "Serverless for intelligence, templates for
  resilience — each where it wins."
- P1 · Evidence: live 65,553-token campaigns, keyless
  quickstart · Missing: SLM cost comparison · Owner: 03 ·
  Status: DONE.

## Cluster 3 — Principal systems engineer

### Q15. What breaks at 10,000 concurrent requests? Measured capacity?

- Vulnerability: scale theater.
- Fix: NO 10k claim. Measured: N=1/5/10 loopback, 0 errors
  (`concurrency-results.md`); documented ceilings (single
  worker, sync SSE, SQLite demo stores).
- Rebuttal: "We publish N=10 with zero errors — and the
  exact ceiling above it."
- P1 · Evidence: concurrency report + honest limits ·
  Missing: N=25/50, soak · Owner: 11 · Status: ACCEPTED.

### Q16. Single point of failure? Degradation?

- Vulnerability: one VM, one Postgres, one worker.
- Fix: documented: VM = SPOF; app degrades to explicit
  errors (no silent partial writes — saga states persist);
  backup/restore TESTED (`10-final-verification.md`).
- Rebuttal: "One VM by design for the prize; recovery
  tested, not assumed."
- P1 · Evidence: restore test record, snapshot · Missing:
  multi-AZ (out of scope) · Owner: 10 · Status: ACCEPTED.

### Q17. Measured memory/CPU/worker footprints?

- Vulnerability: unknown resource profile.
- Fix: bench runs record CPU/RAM shape (small campaign
  tables); production is a 2 vCPU/4 GB VM with headroom
  observed during N=10.
- Rebuttal: "Small, measured, and bored at demo load."
- P2 · Evidence: bench logs · Missing: sustained
  profiling · Owner: 11 · Status: ACCEPTED.

### Q18. Secrets to external inference endpoints?

- Vulnerability: credential exfiltration via prompts.
- Fix: server-side key, never to browser; prompts carry
  intents + capability schemas, never tokens; secrets-scan
  in CI; no secret in exports/video/logs (audited).
- Rebuttal: "Keys live server-side; prompts never see
  them — CI scans every commit."
- P0 · Evidence: CI secrets-scan green, media audit ·
  Missing: none · Owner: 09 · Status: DONE.

### Q19. Idempotency after ambiguous failures/crashes?

- Vulnerability: double effects.
- Fix: idempotency keys + leases + reconcile-on-startup +
  UNKNOWN_OUTCOME tri-state (PRESENT/ABSENT/INDETERMINATE);
  crash matrix 20/20 incl. crash-after-effect.
- Rebuttal: "Crash anywhere — restart reconciles, never
  blindly retries."
- P1 · Evidence: chaos matrix, engine tests · Missing:
  none material · Owner: 06 · Status: DONE.

### Q20. What works without Vultr Inference / offline?

- Vulnerability: cloud dependency for the whole demo.
- Fix: full deterministic path keyless (fresh-clone proof);
  only open-ended planning needs inference, with explicit
  fallback labeling.
- Rebuttal: "Pull the key — the demo still runs, and says
  so on screen."
- P1 · Evidence: fresh-clone test, fallback tests · Missing:
  none · Owner: 03 · Status: DONE.

## Cluster 4 — Live demo saboteur

### Q21. Empty / malformed / contradictory / adversarial input?

- Vulnerability: demo crash on hostile input.
- Fix: Pydantic bounds everywhere (intent ≤8k, users ≤100,
  steps ≤32 in RC8); malformed → 422 with codes; ambiguous
  → CLARIFY; forbidden → REFUSE. Negative matrix tested.
- Rebuttal: "Break the input, get a structured answer —
  never a stack trace."
- P0 · Evidence: negative-matrix + RC8 tests · Missing:
  none · Owner: 12 · Status: DONE.

### Q22. Arbitrary URL / PDF / unsupported resource from a judge?

- Vulnerability: invented browsing/file abilities.
- Fix: NO URL/PDF/file ingestion exists — unsupported input
  is refused with a code, never faked. No fix needed beyond
  honesty (this doc + demo script).
- Rebuttal: "We don't browse or read PDFs — and we say so
  instead of faking it."
- P0 · Evidence: capability registry (closed set) · Missing:
  none · Owner: 15 · Status: DONE.

### Q23. Independent verification of ops and metrics?

- Vulnerability: trust-me demo.
- Fix: every claim re-runnable — offline CLI `verify`,
  exportable Evidence JSON, open eval harness, fresh-clone
  recipe, bench scripts with protocols.
- Rebuttal: "Don't trust the demo — run the verifier."
- P0 · Evidence: CLI, exports, harness in repo · Missing:
  none · Owner: 07 · Status: DONE.

### Q24. Unforgettable visual in the first 15 seconds?

- Vulnerability: slow-burn opening loses judges.
- Fix: V2 opens on a half-failed workflow mid-chaos, then
  INJECT FAILURE → live healing climax ~0:50 (audited
  SHIP-READY; claims TRUE).
- Rebuttal: "Fifteen seconds in, you're watching systems
  break — then unbreak."
- P1 · Evidence: `demo-v2.mp4` + media audit · Missing:
  none · Owner: 19 · Status: DONE.

## Cluster 5 — Grandmaster elevation

### Q25. Optimize a process or remove manual recovery work?

- Vulnerability: incrementalism.
- Fix: category claim grounded in the demo: reverse-order
  compensation + re-verification removes the manual
  cleanup pass for covered cases; MANUAL_REQUIRED stays
  explicit for the rest.
- Rebuttal: "For covered failures, the cleanup ticket
  never gets written."
- P2 · Evidence: COMPENSATED runs with proofs · Missing:
  customer time-saved data · Owner: 17 · Status: ACCEPTED.

### Q26. Genuinely differentiated Vultr use?

- Vulnerability: generic cloud hosting.
- Fix: full stack on 1 Paris VM (API/worker/web/Postgres/
  Caddy) + LIVE Serverless Inference planning (65,553
  tokens measured, model pinned) — both load-bearing.
- Rebuttal: "Vultr computes every step and thinks every
  plan — pull either and the demo tells you."
- P1 · Evidence: infra docs, inference ledger · Missing:
  none · Owner: 02 · Status: DONE.

### Q27. Measurable network effects from real deployments?

- Vulnerability: no flywheel story.
- Fix: HONEST — none claimed. Candidate hypothesis only:
  anonymized failure/compensation corpus improving
  recovery policies (future, labeled as such).
- Rebuttal: "No fake flywheel — but every deployment
  hardens the shared recovery contracts."
- P2 · Evidence: none (hypothesis) · Missing: fleet data ·
  Owner: 16 · Status: WONTFIX (pre-traction).

### Q28. Real regulation creating auditability demand?

- Vulnerability: false legal-mandatory claims.
- Fix: cite-but-don't-overclaim: SOC 2 CC7/CC8 (monitoring,
  change management), ISO 27001 A.12.4 (logging), GDPR
  Art. 5(2)/30 (accountability/records), HIPAA §164.312(b)
  (audit controls) create CONTROL demand; REVERSA is a
  control aid, never "compliance in a box."
- Rebuttal: "Auditors demand trails — we mint them per
  action. Compliance itself stays yours."
- P2 · Evidence: control mapping (this section) · Missing:
  auditor review · Owner: 18 · Status: ACCEPTED.

### Q29. Hardest engineering feat in under 20 seconds?

- Vulnerability: undifferentiated pitch.
- Fix: "Crash the worker mid-compensation — restart —
  watch it reconcile uncertain effects instead of
  double-undoing them." (crash matrix case, re-runnable).
- Rebuttal: "We crash on purpose, on stage, and recover
  on the record."
- P1 · Evidence: chaos matrix case · Missing: none ·
  Owner: 15 · Status: DONE.

### Q30. The one sentence judges should remember?

- Vulnerability: forgettable entry.
- Fix: "Most automation shows what it did — REVERSA shows
  what happened, what was repaired, and what can actually
  be proven." (Strategy A one-liner, V6 selection.)
- Rebuttal: "Reversible where possible. Accountable
  everywhere."
- P1 · Evidence: V6 strategy selection (A=8.70) · Missing:
  none · Owner: 19 · Status: DONE.

## Tally

DONE 14 · ACCEPTED 15 · WONTFIX 1 (Q27) · OPEN 0.
P0 remaining: none. P1 remaining: larger-n evals, N=25/50,
scheduled drift monitor (all documented, none blocking).
