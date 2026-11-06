# RC10 Final Verification Gate — V9 TITAN-1

Date: 2026-11-06. Release: `0.2.0-rc.10`, tag `v0.2.0-rc.10` on `da73559`.

## Code gates (local)

- API suite: **792 passed, 2 skipped, 0 failed** (111 s; 787 V8 + 5 new:
  `test_sse_hold.py` +4 incl. un-xfailed reproducer, `test_evidence_shared_view.py` +1).
- SSE lease fix: `_StreamLease` + `weakref.finalize`; exactly-once release;
  429-before-stream + cap 32 preserved. V8 strict-xfail removed after XPASS
  on the original reproducer.
- Shared view: 8 redactions (approvals actors omitted); events byte-identical
  → CLI still VALID; view stays INTERNAL/DO-NOT-POST.
- Frontend: `next build` green locally and in CI.

## CI gates (GitHub Actions, main)

- `42157034167` (RC10 `da73559`): SUCCESS (api, web, docker, secrets-scan).

## Production gates (https://217.69.7.155.nip.io, RC10 deployed)

- Pre-deploy backup `reversa-2026-11-06T03-33-59Z-*` + tree snapshot
  `/root/reversa.pre-rc10-20261106-0335`; `.env` preserved.
- `/readyz`: `ready:true`, `version 0.2.0-rc.10`. Web 200.
- Smoke wf93: **COMPLETED**, 59 events.
- Shared view live: 8/8 redactions, approvals actor-free, 59/59 events identical.
- SSE terminal replay live: `done` in 0.6 s.
- Chaos wf94 (`http500` x10 on billing): **COMPENSATED**, 81 events,
  recovery-manifest 200.
- Offline CLI verify: smoke VALID (59), shared VALID (59), chaos VALID (81).

## Verdict

**READY — SUBMISSION ACTION REQUIRED** (human-only LabLab filing, see
`SUBMISSION-ACTION-REQUIRED.md`).
Known limitations unchanged: single-model planner, A/B n=12, N≥25/50 +
soak + external pentest not done, shared view internal-only
(commitment format deferred), V2 video ships (V3 NO-GO re-confirmed),
wf41 left in place by design.
