# 04 — Real-execution proof

Nothing is animated. Every claim below is reproducible in the live app or the
test suite (`pytest reversa/apps/api/tests`, `smoke_browser.py`).

1. **Real resources:** `/api/v1/demo/{crm,identity,support,billing,notify}/resources`
   shows rows created by runs (org, workspace, 4 users, queue, billing
   profile). Query before, during, after.
2. **Real failures:** Demo Lab injects HTTP 500/429, timeouts, malformed
   responses, latency, crashes — consumed as one-shot rules, demo tenant only.
3. **Real compensation:** billing-500 run ends COMPENSATED: 7 actions undone
   in reverse order (verified absent afterwards — workspace hard-deleted,
   users/org/queue archived), 2 dependents SKIPPED. Order asserted in tests.
4. **Real reconciliation:** timeout run passes through UNKNOWN_OUTCOME,
   confirms absence, retries idempotently (no duplicates), ends COMPLETED.
5. **Real races:** 5 threads claim one action — exactly one wins (test).
6. **Real restarts:** startup reconciliation converts stale CLAIMED/EXECUTING/
   VERIFYING/COMPENSATING rows to safe states (tested at unit + boot).
7. **Real evidence:** 59-event chain per happy run, SHA-256 linked, verified
   by API and offline CLI (`python -m reversa_api.cli verify`).
   Verifier semantics: VALID means prefix-consistency (exported events 1..N
   hash-link back to GENESIS with no gaps or mismatches). It does not rule
   out trailing truncation (events after N removed pre-export still verify
   VALID), and exported `ts` timestamps are not hash-covered. Strict mode
   (`verify --strict` with `--expect-count N` and/or `--expect-head <hash>`)
   fails closed without caller-supplied anchors (either anchor alone
   suffices) and checks them when given.
