# 20 — Final competition readiness (V11, 2026-11-06)

No code changed this cycle (docs + verification only). RC10
(`v0.2.0-rc.10`, `da73559`) stays the submission release. No RC11.

## A. Submission

Status: NOT confirmed — human-only filing, see
`SUBMISSION-ACTION-REQUIRED.md` (deadline Mon 2026-11-09 00:00 Paris,
dashboard value wins). Package re-verified: mp4 85.19 s h264/aac, srt,
slides, covers, texts, 0 broken doc links, MIT, Challenge 2, Vultr-hosted.

## B. Engineering (V11 delta)

- R12: prod `api_tokens` inventory = 1 row (`jury`, org 1, Nov 5) — no
  orphans (hashes never printed). Full hash-absence proof needs the
  divulged value (not hunted); owner rotation post-submission advised.
- GitHub connector: re-audited — deny-by-default + INDETERMINATE test
  present, but no token/allowlist on the VM → stays honestly unconfigured.
- Gaps A/C/D re-confirmed deferred with reasons (migration risk / credit
  budget / demo risk). V3 NO-GO re-confirmed (no browsers/recorder).
- Board: 57 submissions, ARC still the only verified Challenge 2 rival.

## C. Business (NEW)

- `docs/product/beachhead-and-roi.md`: ranked beachhead (primary:
  Business Systems ops; secondary: SaaS provisioning) + parameterized
  ROI formula + sensitivity + pre-registered pilot metrics.
- `docs/product/value-prop.md`: one-page exec prop, elevator pitch,
  build-vs-buy, 4 objections with honest answers, zeros stated.
- All buyer figures labeled hypotheses; no traction invented.

## D. Jury

Pitch, demo script, V2, slides, matrix 16, gauntlet 13 + delta 17 all
current. Elevator (30 s): "AI agents automate work across systems.
REVERSA makes that work accountable: every action verified, recoverable
failures safely compensated, every outcome carrying evidence."

## E. Scorecard (internal estimates, evidence-backed)

| Dimension | Score | Strongest proof | Biggest objection |
|---|---|---|---|
| Technology | 9 | rc.10 live, 792 tests, wf93/94 + 3× VALID | A/B n=12 only |
| Presentation | 8 | START-HERE, V2, live demo | V3 absent |
| Business Value | 8 | beachhead + ROI + pilot (NEW) | zero customers |
| Originality | 9 | typed comp + tri-state + passport | ARC adjacent space |
| AI correctness | 7 | A/B + gate + provenance | n=12, no tool-F1 |
| Security | 8 | lease fix, isolation tests, R12 bounded | no ext pentest |
| Reliability | 8 | 20/20 chaos, backup+snapshot | N=10 ceiling, 1 VM |
| Reproducibility | 9 | fresh-clone + CLI + 792 | RC7-clone only |
| Product maturity | 9 | full flow + 10/10 smoke | minor UX rough edges |
| Compliance | 9 | MIT, C2, package frozen | filing pending |

Business 7→8 on packaging strength alone; no other score moved without
new runtime evidence. Verdict: **READY — SUBMISSION ACTION REQUIRED.**
