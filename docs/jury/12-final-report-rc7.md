# 12 — Final report RC7 (2026-11-06)

Release candidate `0.2.0-rc.7`, tag `v0.2.0-rc.7` on `5dac22a`.
Docs HEAD at writing: `1e5ba31`. CI green on every RC7 commit.
Prod `https://217.69.7.155.nip.io` serves rc.7, verified healthy.

## A. Executive summary

RC7 closes the V5 ascent: joint API+web version bump, revoked-token
persistence that survives restarts, a measured concurrency campaign,
a real backup/restore test on prod data, a fresh-clone reproduction,
and LabLab texts synced to measured numbers. No code feature was
added for the jury that is not deployed and verified. The only
remaining submission step needs the human's LabLab account.

## B. Vultr Inference proof (no secrets)

- Prod model: `deepseek-v4.1-flash-1017` via
  `https://api.vultrinference.com/v1`, live in prod.
- Decision-eval: 2x10 live cases, 31,975 tokens, JSON 100% valid,
  DAG 100% valid; invalid drafts rejected, never executed.
- Prompt A/B (2026-11-06, 12 cases, 33,578 tokens): prompt A
  10/12 = 0.833 kept in prod; B (protocol_v5) 11/12 = 0.917 stays
  experimental (+19% tokens, simple-legit regression).
  Combined live tokens: 65,553.
- Real AI plan accepted in prod via guest intent (201, 10 steps,
  accepted after 2 attempts); malformed AI drafts rejected 422.
- Provenance (provider/model/attempts) is shown in the product;
  deterministic baseline stays the default with explicit fallback.
- Limits: A/B n=12 is small; single prod model; no claim of
  general planning superiority beyond the measured evals.

## C. Implemented improvements (RC7 commits)

| Commit | Content |
|---|---|
| `5dac22a` | Code: API+web joint bump to `0.2.0-rc.7` |
| `fb6b033` | Docs: CHANGELOG, A/B record, gate sync |
| `be9bd6a` | Infra: revoked-hashes passthrough into api container |
| `982d9f9` | Bench docs: concurrency N=1/5/10 campaign |
| `d6f2ac3` | Gate: restore-test + concurrency record |
| `1415c12` | Fresh-clone PASS record + README 771 |
| `1e5ba31` | LabLab texts RC7 sync + keep-V2 decision |

Tag `v0.2.0-rc.7` (annotated) on the code commit `5dac22a`,
same convention as rc.6.

## D. Security & reliability

- Token rotation: historic `demo` token revoked (`remaining=1`,
  `jury` by design); revocation hash persisted to server `.env`
  only (counts in reports, never values); compose passthrough
  added after discovery that the container never read the var
  (`env_revoked_count` 0 -> 1, mint post-restart 201).
- Backup/restore (2026-11-06, prod data, prod never stopped):
  fresh `backup.sh` pair; dump restored into an isolated temp
  postgres — 7/7 table counts identical (53 wf / 525 actions /
  3275 events), wf85 COMPLETED + wf86 COMPENSATED present;
  5/5 sqlite `integrity_check` OK; api image booted on restored
  data -> `/healthz` 200 `db:true`; all temp artifacts removed;
  prod re-verified healthy from outside.
- Concurrency (isolated loopback, NVMe): N=1/5/10, all COMPLETED,
  59 events each, offline CLI VALID, 0 errors, 0 x5xx, 0 locks.
  Honest bias note: +1 s poll granularity in raw exec figures;
  adjusted N=1 (~183 ms) matches the V2 baseline (192 ms).
  First N=5 on HDD (WD Green 5400 rpm) was ~9x slower with
  identical correctness — environmental, documented, not a
  regression. A public-mint follow-up correctly returned 429
  (5/hour/IP bucket works; excluded, not retried).
- Fresh-clone (clone of `d6f2ac3`, no key): venv install OK, API
  boots with demo token in log, public mint -> intent -> approve
  -> execute -> COMPLETED (59 events, CLI VALID), pytest
  **771 passed / 2 skipped** (matches RC7 record), web
  `npm install` + `next build` PASS, served homepage 200.
  Temp clone removed after.
- Not done: N=25/50 saturation, sustained soak, external
  pentest, snapshot-restore on a second VM (app-level restore
  tested instead; snapshot `complete` untouched).

## E. Jury demonstration

1. Open the public URL, click Launch Demo (no token).
2. Submit an onboarding intent, review Shadow Preview, approve.
3. Watch 10 verified steps across 5 systems, then INJECT FAILURE.
4. Watch detection, dependent blocking, reverse-order
   compensation, re-verification.
5. Open Evidence, download JSON, verify offline with
   `python -m reversa_api.cli verify` (exit 0, chain recomputed).

## F. Commercial positioning

**The verified recovery layer for enterprise AI operations.**
Buyers: CTO, VP Engineering, Head of IT/Business Systems,
RevOps, MSPs. 30-day pilot: connect one workflow, measure
recovery time and manual interventions before/after. ROI
simulator keeps MEASURED / HYPOTHETICAL strictly separated;
no invented customers or revenue. Details: `08-business-case.md`.

## G. Internal evaluation (target 10/10, scored honestly)

| Category | Score | Proof / gap |
|---|---|---|
| Technical Execution | 10 | Full path verified live + fresh-clone |
| Reliability | 9 | N<=10 only, no soak, sync SSE |
| Security | 9 | Rotation done, isolation tested; no ext. pentest |
| AI Integration | 9 | Live evals + A/B; n=12 small, single model |
| Product Experience | 9 | Jury Mode 1-click; V2 video, no fresh a11y audit |
| Originality | 9 | Recovery Proof + Evidence; no world-first claim |
| Business Value | 8 | Strong case, hypothetical ROI, zero customers |
| Reproducibility | 10 | Fresh-clone PASS end to end |
| Jury Presentation | 9 | V2 SHIP-READY, texts ready; deposit pending human |
| Hackathon Compliance | 9 | All verified except the LabLab deposit itself |

## H. Hackathon compliance

- Challenge 2, original code, MIT license, public repo + demo.
- Vultr: Cloud Compute (full stack) + Serverless Inference
  (live planning) on Paris VM; spend $0.28 observed 2026-11-05,
  on track <$3 total (target <$140 of $200 credit).
- Video `demo-v2.mp4` (85 s, narrated, SRT, audited, no secrets),
  slides PDF (10 pp.), cover, 12-capture gallery.
- Cutoff: 8/9 Nov ambiguity unresolved from public pages —
  dashboard re-check is a human step; submit early.

## I. GitHub

- Branch `main`, HEAD `1e5ba31` (+ this report commit).
- Tag `v0.2.0-rc.7` -> `5dac22a` (verified via ls-remote).
- CI: success on `be9bd6a`, `982d9f9`, `d6f2ac3`, `1415c12`,
  `1e5ba31` (4/4 incl. secrets-scan where applicable).
- Links: repo `toskaman/reversa`, demo
  `https://217.69.7.155.nip.io`.

## J. Final verdict

**READY WITH KNOWN LIMITATIONS.**

Ready: deployed RC7 verified end to end, evidence-backed docs,
reproducible from a fresh clone, submission package complete.
Limitations: LabLab deposit needs the human account; N>=25 /
soak / external pentest not run; A/B n=12; V3 video not built
(V2 ships). No `READY` without the deposit confirmation.
