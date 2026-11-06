# RC9 Final Verification Gate — V7 TITAN-1

Date: 2026-11-06. Release: `0.2.0-rc.9`, tag `v0.2.0-rc.9` on `3ea39ee`.

## Code gates (local)

- API suite: **786 passed, 2 skipped, 0 failed** (113 s; 778 RC8 + 8 new:
  `test_sse_hold.py` 4, `test_evidence_shared_view.py` 4).
- B2 SSE: idle 120 s → 30 s, heartbeat ~2 s, max 32 concurrent streams
  (429 + Retry-After); `EventTimeline` resumes via `since_seq` (≤3),
  silent stop on `done`.
- B1 shared view: `?view=shared` omits name/intent/plan/inputs/output/error
  (listed in `redactions`); events byte-identical → CLI still VALID.
- Frontend: `tsc --noEmit` + `next build` green locally and in CI.
- wf41: read-only classified, disposition filed
  (`.agents/reviews/wf41-disposition.md`), left in place untouched.

## CI gates (GitHub Actions, main)

- `42147652486` (RC9 `3ea39ee`): SUCCESS (api, web, docker, secrets-scan).

## Production gates (https://217.69.7.155.nip.io, RC9 deployed)

- Pre-deploy backup + tree snapshot taken, `.env` preserved.
- `/readyz`: `ready:true`, `version 0.2.0-rc.9`. Web 200.
- Smoke wf90: **COMPLETED**, 59 events, RT-04 `decided_by=guest:…` OK.
- Shared view live: intent omitted, 59/59 events identical, 6 redactions.
- SSE terminal replay live: `done` in 0.6 s.
- Chaos wf91 (`http500` x10 on billing): **COMPENSATED**, 81 events,
  recovery-manifest 200.
- Offline CLI verify: smoke VALID (59), shared VALID (59), chaos VALID (81).

## Verdict

**READY — SUBMISSION ACTION REQUIRED** (human-only LabLab filing).
Known limitations unchanged: single-model planner, A/B n=12, N≥25/50 +
soak + external pentest not done, V2 video ships (V3 storyboard only),
wf41 left in place by design.
