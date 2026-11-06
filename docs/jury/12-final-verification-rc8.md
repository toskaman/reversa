# RC8 Final Verification Gate — V6 TITAN-1

Date: 2026-11-06. Release: `0.2.0-rc.8`, tag `v0.2.0-rc.8` on `de61d1c`.

## Code gates (local, pristine archive)

- API suite: **778 passed, 2 skipped, 0 failed** (105 s, zip-pristine tree).
- New regression module `tests/test_redteam_v6_fixes.py`: 7/7 pass.
- Fixes: mint rate-limit tier exact match (RT-V5-01), public-mint window cap 5/h/IP
  oldest-first (RT-V5-05b/07), SSE ticket cap 1000 + reset helper (RT-V5-07/08),
  approver = authenticated actor with `decided_by_label` metadata (RT-V5-04),
  `MAX_PLAN_STEPS=32` + strict `_type_matches` + dependency-type strictness (RT-V5-10).

## CI gates (GitHub Actions, main)

- `42140236952` (code `06651ab`): SUCCESS.
- `42140668377` (docs `de61d1c`): SUCCESS.

## Production gates (https://217.69.7.155.nip.io, RC8 deployed)

- `/readyz`: `ready:true`, `version 0.2.0-rc.8`. Web 200.
- Smoke wf87: **COMPLETED**, 59 evidence events.
  RT-04 live proof: durable `decided_by=guest:944b5491f7bcf5f3`,
  event label `rc8-prod-smoke` preserved.
- Transient-fault resilience wf88: single `http500` absorbed by bounded retry →
  **COMPLETED** (designed behavior, not a gate failure).
- Chaos wf89 (`http500` x10 on billing): **COMPENSATED**, 81 evidence events,
  recovery-manifest 200.
- Offline CLI verify: `rc8_evidence_smoke.json` VALID (59 recomputed),
  `rc8_evidence_chaos.json` VALID (81 recomputed). Exit 0 both.

## Pre-existing, untouched

- wf41 RUNNING / UNKNOWN_OUTCOME (guest org, since 2026-11-05): chaos leftover
  from an earlier cycle, fleet-wide query before RC8 deploy. Left as-is for
  manual disposition; not caused by RC8.

## Verdict

**READY WITH KNOWN LIMITATIONS** (unchanged from RC7 report):
single-model planner, A/B n=12, N>=25/50 + soak + external pentest not done,
LabLab deposit human-only.
