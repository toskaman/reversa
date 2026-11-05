# REVERSA — Final report RC6 (V3 objective, §25)

Date: 2026-11-05. Release: `0.2.0-rc.6` (tag `v0.2.0-rc.6`).
Code HEAD: `db99170`; docs HEAD: `dbb9a6b` (this report).
CI green on all three: `42115552403`, `42116258339`, `42116992871`.
Prod: https://217.69.7.155.nip.io (`healthz` ok, `db:true`, version `0.2.0-rc.6`).
Repo: https://github.com/toskaman/reversa (MIT). No secrets in this file.

## A. Executive Summary

What changed in V3: real Vultr Serverless Inference drives plan
generation in production (`deepseek-v4.1-flash-1017`, validated or
rejected — never silently executed); Cycle 2 made the planner agentic
(structured clarification, explicit refusal, offboarding/escalation
templates); RC6 lets jury guests inject their own org-scoped chaos
(cap 50/org, auto-cleaned), so the Recovery Moment needs zero tokens.

Why it is better: every claim below re-runs from the repo or the live
app — 689-test suite, 10/10 browser smoke on prod, 20/20 chaos matrix,
2×10 live AI eval, offline evidence verifier. Nothing is animated.

Competitive edge (demonstrated, not asserted): AI proposes,
the deterministic engine disposes, and the Recovery Proof Engine shows
before/during/after resources with a verdict it can defend —
including documented `INDETERMINATE` / `MANUAL_REQUIRED` refusals.

## B. Vultr Inference proof

- Endpoint `https://api.vultrinference.com/v1`, model requested ==
  served (`deepseek-v4.1-flash-1017`, substitution checked).
- Live prod runs wf80/wf81: COMPLETED, 9/9 actions VERIFIED, hash
  chain VALID (see `04-real-execution-proof.md`).
- Campaign `docs/benchmarks/ai-eval-live-RESULTS.md`: 2×10 cases,
  15,387 + 16,588 = 31,975 tokens, completed, no early stop.
- Malformed AI drafts rejected 422, never executed; deterministic
  baseline remains the labeled default with explicit fallback.
- Limits (stated): per-call inference USD not split out (tokens only,
  no price table applied); single primary model, no secondary.
  Account-level spend observed $0.28 on 2026-11-05 ($200 credit).

## C. Implemented improvements (V3 commits)

- Cycle 1 Real Inference: authenticated provider, JSON-mode plans,
  provenance + latency recorded, 422 repair loop.
- Cycle 2 Agentic (RC5 `0cecb98`): clarify/refuse contracts,
  offboarding + escalation templates, live-eval docs (`f1ac562`).
- RC6 (`db99170`): guest org-scoped chaos + per-org cap 50 (429),
  agentic smoke (clarify flow asserted), version bump.
- Docs: CHANGELOG RC5+RC6 (`3cd3c6d`), LabLab package + 12-shot
  gallery (`dbb9a6b`), this report.
- All merged to `main` with green CI; prod redeployed and re-smoked.

## D. Security & reliability

Campaigns (observed): 689 passed / 2 honest skips; prod smoke 10/10,
0 console errors; guest A/B isolation (read/modify/approve/execute/
evidence/SSE/chaos-scope denied across sessions); quota-410; expired
tokens refused; live guest chaos 201 then cleaned; chaos matrix 20/20.

Fixes this cycle: guest chaos 403 → scoped allow + cap 50 + sweep;
smoke hardened for agentic clarify path; RC5 rsync incident → never
`--delete` on `/root/reversa` again, `.env` restored from containers.

Open/accepted: old demo token treated as disclosed (rotation not
re-confirmed this cycle); no external pentest; soak tests not run.

## E. Jury demonstration (exact path, zero token)

1. Open https://217.69.7.155.nip.io → Launch Interactive Demo.
2. Command Center → Generate plan (Acme) → Shadow Preview → Approve.
3. Execute → watch graph + SSE timeline; check Connector Hub rows.
4. Demo Lab → INJECT FAILURE + RUN (works as guest since RC6).
5. Watch detection → dependents blocked → reverse-order compensation.
6. Resources view: workspace deleted, users/org/queue archived.
7. Evidence Passport → VALID → download JSON → offline CLI verify.
8. Time Machine (before/during/after) + Execution Comparison pages
   read the same real event streams (race page labeled descriptive-only).

## F. Commercial positioning

Buyers: Head of IT / RevOps / Business Systems at 200–2000-person
SaaS + MSPs running onboarding/support ops. Wedge: teams already
automating (Zapier/n8n/Temporal) that eat recovery cost.
Differentiator: typed compensation + reconciliation + evidence in one
platform, AI planning fenced by policy. Land: 1-click demo → one
sandbox system → paid pilot on recovery hours saved. All economics
are labeled hypotheses on `/roi` (MEASURED vs HYPOTHETICAL split);
no customers, revenue, or savings claimed.

## G. Internal evaluation (self-scores, not jury scores)

| Category | Score | Proof | Limitation / remaining |
|---|---|---|---|
| Technical Execution | 9/10 | 689 tests, green CI ×3, prod re-smoked | Concurrency beyond sequential baselines not re-run on RC6 |
| Reliability | 9/10 | 20/20 chaos, guest chaos live, UNKNOWN reconciliation tested | No soak/long-run campaign this cycle |
| Security | 8/10 | A/B isolation, caps, scoped chaos, secret scans clean | Old-token rotation unconfirmed; no external pentest |
| AI Integration | 9/10 | Live plans, 2×10 eval, provenance UI, 422 honesty | USD cost unknown; single model |
| Product Experience | 9/10 | 10/10 smoke, 1-click Jury Mode, honest labels | V3 video missing; no formal mobile/a11y audit |
| Originality | 9/10 | Recovery Proof + verifiable evidence loop | Self-assessed; rivals not re-audited this cycle |
| Business Value | 8/10 | Case + ROI sim, labeled hypotheses | No pilot/customer validation (hackathon-inherent) |
| Reproducibility | 9/10 | No-key quickstart, offline verifier, fresh CI | Full fresh-clone run by a third party not done |
| Jury Presentation | 8/10 | V2 video ship-ready, 12 gallery, slides, script | V3 video storyboard-only; submission not filed |
| Hackathon Compliance | 9/10 | MIT, Vultr-native, original, docs complete | Submission pending human; cutoff hour unconfirmed |

Official criteria: Application of Technology 9, Presentation 8,
Business Value 8, Originality 9 — same evidence and gaps as above.

## H. Hackathon compliance

Challenge 2, Powering the Future of Work. Backend + web + worker +
Postgres on one Vultr VM (Paris, `vc2-2c-4gb`); Vultr Inference live
(optional for Ch.2, shown real). Original code, MIT, public repo,
video + slides + gallery + texts ready. Submission on LabLab is
mandatory and still requires the human account — NOT claimed.
Cutoff: 8 Nov, exact hour unconfirmed (dashboard check pending).

## I. GitHub

- Branch `main`, code `db99170`, docs `dbb9a6b`, tag `v0.2.0-rc.6`.
- CI success: `42115552403` (RC6) · `42116258339` · `42116992871`.
- Links: repo, demo URL, `docs/jury/` dossier, gallery, video V2.

## J. Final verdict

**READY WITH KNOWN LIMITATIONS** — ship-ready for LabLab filing by
the human; V3 video and USD inference pricing remain open items.

### §24 exit checklist (honest state)

- [x] Key configured, never exposed (server-side only, scans clean).
- [x] Authenticated calls succeed; real AI plans generated + proven.
- [x] Provenance shown; invalid plans refused; fallback labeled.
- [x] Main workflows operate; execution + compensation verified.
- [x] Recovery Proof coherent; Evidence validated independently.
- [x] Full tests on final HEAD; CI green; no critical defect open.
- [x] Vultr infra live; public demo reachable; Jury Mode works.
- [x] No secrets exposed; video/slides/docs/business-case in sync.
- [ ] LabLab submitted (human account) — package ready, not filed.
- [ ] Cutoff hour confirmed on dashboard — pending human check.
- [x] Independent internal evaluation published (section G above).
