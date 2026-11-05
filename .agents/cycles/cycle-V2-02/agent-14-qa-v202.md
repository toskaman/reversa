# AGENT-14 — QA, REVERSA V2 cycle 2

## Identity

- Agent: AGENT-14, QA Engineer
- Cycle: REVERSA V2 cycle 2
- Mode: READ-ONLY (only this report file written; no source or test files touched)
- Date (UTC): 2026-11-05
- Repo root: `D:/Hackatons/Vultr`
- Suite under test: `reversa/apps/api` (pytest, `testpaths = ["tests"]`)
- Observation window: V2-02 backend code landed continuously during this QA
  pass (51 → 139 collected items across runs). Every count below is tied to
  the run that produced it; the FINAL verdict is run 8.

## Mandate

Run the FULL backend suite, collect per-file results, list new weak
assertions and untested routes among V2-02 additions. Read files before
citing. Never invent results. Never commit secrets. Do not push.

## Files read

Tests — all 14 files read in full (10 pre-existing + diffs, 4 brand new):

- `reversa/apps/api/tests/conftest.py` (unchanged fixtures)
- `test_api_happy.py` (1 test, unchanged), `test_chaos.py` (4, unchanged),
  `test_planner_evidence.py` (5, unchanged), `test_security.py` (18, unchanged)
- `test_engine_units.py` — full re-read incl. 10 new resume tests (diff + body)
- `test_github_contract.py` — full re-read incl. 20 new allowlist/registration
  tests (diff, both halves)
- `test_ai_eval.py` — full re-read incl. 6 new offline metering tests (diff + tail)
- `test_chaos_matrix.py` (NEW, 5 tests, full), `test_health.py` (NEW, 5, full),
  `test_demo_isolation.py` (NEW, 3, full), `test_guest_sessions.py` (NEW, 12, full),
  `test_recovery_manifest.py` (NEW, 10, full), `test_cli_verify.py` (NEW, 14, full),
  `test_perf_regressions.py` (NEW, 3, full)

Source (endpoint inventory + behavior contracts for V2-02 additions):

- `routes/workflows.py` (base full-read + `HEAD` diff: resume route, list N+1 fix)
- `routes/recovery.py` (NEW, read to line 500 + endpoint contract via tests)
- `routes/guest_sessions.py` (NEW, full), `routes/health.py` (base + diff),
  `routes/chaos.py`, `routes/evidence.py`, `routes/connectors.py` (full)
- `auth.py` (full at two revisions: broken mid-edit rev + final 15 KB rev),
  `main.py` (diff: 2 routers + 2 middlewares)
- `engine/saga.py`, `engine/states.py`, `connectors/github.py`,
  `connectors/services.py`, `planner/vultr.py` (all via `HEAD` diff)
- Spec: `docs/benchmarks/chaos-matrix-v2.md` (CM-01–CM-18 table)
- Prior: `.agents/cycles/cycle-V2-01/agent-14-qa-baseline.md`,
  `.agents/cycles/cycle-V2-02/agent-10-rc-plan.md` (G1 gate = 49/2 on clean base)

## Files modified

- `.agents/cycles/cycle-V2-02/agent-14-qa-v202.md` (this file) — ONLY write.

## Commands run

All with `reversa/apps/api/.venv/Scripts/python.exe -m pytest`
(Python 3.14.4, pytest 9.2.0). Tree was churning (parallel agents); each run
is a timestamped sample, oldest to newest:

1. `pytest tests -v` → **49 passed, 2 skipped** (51 items, 30.80 s).
   Tree then: V2-02 frontend-only changes; backend still at V2-01 base.
   Matches agent-10's G1 baseline exactly.
2. `pytest tests -q --durations=8` → **54 passed, 2 skipped** (32.15 s).
   `test_chaos_matrix.py` (5 tests) landed mid-run.
3. `pytest tests -q` → **65 passed, 2 skipped** (35.07 s).
   Health (5) + AI-eval metering (6) landed.
4. `pytest tests -q` → **3 failed, 95 passed, 2 skipped** (46.40 s).
   `NameError: _lookup_guest` at `auth.py:73` — P1-AUTH-02 guest fallback
   landed without its helper (mid-edit breakage, owner-fixed later).
   Failures: `test_bad_token_rejected`,
   `test_demo_resources_bad_token_rejected`, `test_stream_ticket_requires_auth`.
5. `pytest tests --co -q` → **collection ERROR** (`SyntaxError: unmatched ')'`,
   `auth.py:372`). Same in-flight auth edit, caught mid-save. Retried after
   30 s: `import reversa_api.auth` → OK (file complete at 15 831 bytes).
6. `pytest tests -q --tb=short -rf` → **122 passed, 2 skipped** (46.88 s).
   Auth fixed; engine resume (+10), github allowlist (+20), demo isolation
   (+3), recovery manifest (+10), CLI verify (+14) all landed.
7. Per-file loop (`pytest tests/<file> -q --tb=no`, 12 files) → counts in
   table below; sum 122 passed, 2 skipped. (Guest + perf files did not exist
   yet at loop time.)
8. `pytest tests/test_guest_sessions.py tests/test_perf_regressions.py -q`
   → **15 passed** (2.79 s). New files confirmed green in isolation.
9. FINAL `pytest tests -q --tb=short` → **137 passed, 2 skipped** (36.36 s).
   139 collected = 122 + 12 guest + 3 perf + 2 pre-existing skips. **Zero
   failures. This is the reported verdict.**

Plus: `git status`/`git diff HEAD` snapshots (api scope), `rg` sweeps for
route coverage (`/api/v1/me`, `/api/v1/connectors`, `since_seq`, `guest`,
`resume`, approval-expiry), env-var check (no GitHub/Vultr secrets in env;
both skips honest).

## Observed results

### Final suite: 137 passed, 2 skipped, 0 failed (run 9)

| File | Tests | Passed | Skipped | Delta vs V2-01 base |
|---|---|---|---|---|
| `test_ai_eval.py` | 8 | 7 | 1 | +6 (offline Vultr metering) |
| `test_api_happy.py` | 1 | 1 | 0 | — |
| `test_chaos.py` | 4 | 4 | 0 | — |
| `test_chaos_matrix.py` | 5 | 5 | 0 | NEW (CM-03/04/05/09/10) |
| `test_cli_verify.py` | 14 | 14 | 0 | NEW (strict-verify semantics) |
| `test_demo_isolation.py` | 3 | 3 | 0 | NEW (F2 run scoping) |
| `test_engine_units.py` | 18 | 18 | 0 | +10 (resume paths + route) |
| `test_github_contract.py` | 33 | 32 | 1 | +20 (allowlist/registration) |
| `test_guest_sessions.py` | 12 | 12 | 0 | NEW (P1-AUTH-02 + limits) |
| `test_health.py` | 5 | 5 | 0 | NEW (honest 503 contract) |
| `test_perf_regressions.py` | 3 | 3 | 0 | NEW (F1/F2/F3 statement locks) |
| `test_planner_evidence.py` | 5 | 5 | 0 | — |
| `test_recovery_manifest.py` | 10 | 10 | 0 | NEW (RPE v1) |
| `test_security.py` | 18 | 18 | 0 | — |
| **Total** | **139** | **137** | **2** | **+88 tests vs base (49→137)** |

- Both skips are the pre-existing honest ones (Vultr provider, GitHub live).
  No new skips: G1 "no new skips" criterion holds.
- Standing warning unchanged (pre-existing Starlette/httpx deprecation).
- V2-02 src additions observed in tree: `POST /workflows/{id}/resume`,
  `GET /workflows/{id}/recovery-manifest` (+ `evaluate_recovery`),
  `POST /demo/guest-sessions`, `GET/POST/DELETE /demo/tokens`,
  `GuestSessionMiddleware`, `RateLimitMiddleware` (+ `ratelimit.py`),
  health 503/`ready` flag, F2 run-scoped `DemoStore` + `workflow_id` filter
  param, GitHub allowlist/registration/idempotency honesty, Vultr metering +
  substitution detection, CLI `--strict` anchors, list GROUP-BY count fix,
  `VERIFYING → UNKNOWN_OUTCOME` transition, `evidence.py`/`db.py` query-shape
  fixes (F1/F2/F3).

### V2-02 assertion quality: strong overall, 6 new minor weaks

Strong (exact states/codes/counts, behavior-not-prose): resume stats pins
(`requeued == 1`, `attempt == 1`), allowlist exact codes
(`GITHUB_REPO_NOT_ALLOWED`, `GITHUB_NOT_CONFIGURED`) with no-network proofs,
quota/ratelimit exact bodies (`QUOTA_EXHAUSTED`, `RATE_LIMITED` +
`Retry-After`), health exact-body match, manifest exact rules (C0–C7) +
event-ref resolution, CLI exact messages, statement-count locks with
behavior-equivalence checks.

New weak assertions among V2-02 additions (all minor, none blocking):

1. W1 `test_no_server_side_idempotency_claimed` — asserts a module constant
   is `False`; alone it tests a literal. Mitigated: the companion
   `test_create_sends_no_idempotency_header` pins the actual wire behavior.
2. W2 `test_require_allowed_repo_returns_normalized` — sets the env allowlist
   but passes an explicit tuple, so the `None → env resolution` path of
   `require_allowed_repo` itself is untested (only covered indirectly).
3. W3 `test_resume_route_rejects_terminal_and_ready` — both 409s are
   status-only; the `detail` shape ("nothing to resume" vs "only
   interrupted…") is unpinned. Same for the 409 in
   `test_non_terminal_workflow_is_refused` (this one DOES pin
   `detail.code == R4_NOT_TERMINAL` — resume should do likewise).
4. W4 Magic-seq brittleness inherited by CM-03/CM-04 (`by_seq[6]`,
   compensation tuples `(1..5,7,8)`, `SKIPPED (9,10)`): correct today, but
   any planner-template insert/reorder false-fails. Same standing caveat as
   the V2-01 chaos test.
5. W5 `GuestMintIn` bounds (`ge=1, le=limits`) untested: mint with
   `max_workflows=0` or huge values (422 shape) has no test.
6. W6 Overlap, not weakness: `test_cm05_*` duplicates
   `test_lost_response_retries_idempotently` (same crash×1 on
   `crm.validate_customer`) plus a `CHAOS_CRASH` code pin and resource
   checks. Keep both, but note the maintenance pair.

Carried-over V2-01 weaks (still present, unchanged files): misnamed
`test_concurrent_modification_blocks_compensation` (store-level only; CM-14
e2e still MISSING per spec); label-removal disjunction (`or`);
auth-guard status-only asserts in `test_security.py` (partly superseded:
guest/quota/ratelimit tests DO pin `code` bodies); prose-fragile honesty
assert (`"delete" not in NOTE…`).

### Untested routes among V2-02 additions: NONE

All 6 new V2-02 endpoints are hit by tests (verified by reading both sides):

- `POST /workflows/{id}/resume` — 2 route tests (recover→COMPLETED with
  stats; 409 on READY/terminal).
- `GET /workflows/{id}/recovery-manifest` — 6 endpoint tests (VERIFIED,
  VERIFIED_WITH_COMPENSATION, R4 409, 404, tamper→INDETERMINATE, divergence)
  + 4 evaluator units.
- `POST /demo/guest-sessions`, `GET/POST /demo/tokens`,
  `DELETE /demo/tokens/{name}` — 12 guest tests (mint shape, demo-owner-only,
  guest-cannot-mint, quotas 410, chaos denied, expiry, isolation, rotation
  overlap + guards, rate-limit 429 + recovery, owner unaffected).
- New middlewares covered through the same tests; `workflow_id` demo-filter
  param covered by F2 tests; health/readyz covered by 5 tests.

Remaining untested surface (for cycle-3 planning, mostly V2-01 carryover):

- Only fully-untested routes left: `GET /api/v1/connectors`,
  `GET /api/v1/connectors/{id}/health` (incl. unknown-connector 404).
  (`/me` is now covered via guest/rotation tests; chaos list/delete via
  CM-09; SSE stream via ticket tests; list-workflows partially via the F1
  perf test.)
- Missing negatives: approve 410-expiry / double-approve / cross-tenant;
  cancel matrix (terminal/nonexistent/cross-tenant/AWAITING); intents 422s
  (empty intent, `use_ai=true` without config); evidence 404/cross-tenant/
  unknown-format; events `since_seq`/cross-tenant; preview cross-tenant;
  list `cursor`/`has_more=true` page-2 path; chaos `REVERSA_CHAOS=0` 403,
  real-tenant list/delete 403, cross-org rule delete 404; stream valid
  `Last-Event-ID` resume + cross-tenant error event; resume cross-tenant 404
  + COMPENSATING-via-route; token mint bound validation (W5).
- Chaos-matrix spec gaps still MISSING: CM-06, CM-07, CM-11, CM-12, CM-13,
  CM-14 (e2e), CM-15, CM-16, CM-17, CM-18. (CM-01–05, CM-08–10 covered.)

## Tests (what exists)

- V2-01 files: happy-path E2E (1), chaos E2E + store unit (4), engine units
  incl. race/reconcile/resume (18), planner/evidence (5), security incl. SSE
  tickets + demo-IDOR guards (18), AI eval baseline + live skip (8).
- V2-02 new: chaos matrix CM-03/04/05/09/10 (5), CLI prefix/strict semantics
  (14), F2 run isolation incl. cross-run compensation fence (3), engine
  resume incl. route (10 of the 18), GitHub allowlist/registration/
  idempotency (20 of the 33), guest sessions + quotas + rotation + rate
  limits (12), health honesty (5), perf statement locks (3), recovery
  manifest endpoint + units (10).

## Issues

- I1 (transient, RESOLVED, no action): suite went red twice mid-cycle from
  the in-flight P1-AUTH-02 edit — `NameError: _lookup_guest` (3 failed,
  run 4) then `SyntaxError` at collection (run 5). Owner completed the edit
  within minutes; runs 6/9 green. Not a test flake; concurrent-edit
  artifact on a shared tree. Final verdict unaffected.
- I2 (observation, not mine to fix): `routes/health.py` and
  `tests/test_health.py` are STAGED in the git index (`M `/`A `) while
  everything else is unstaged — a partial `git add` by another agent.
  Release engineer should confirm the intended commit set before tagging.
- I3: `GET /api/v1/connectors*` remains the only route family with zero
  tests; it also feeds the web Connector Hub page.
- I4: CM-14 e2e + CM-15 (`MANUAL_REQUIRED` engine paths) still untested —
  the engine can produce states no test ever drives.

## Risks

- R1. Tree churn: +88 tests and ~1100 src insertions landed DURING this QA
  pass. Counts are correct as of run 9; anything landing after needs a fresh
  `pytest` before RC tagging.
- R2. In-memory stores multiply: SSE tickets, guest sessions, rate limits
  are all single-process. Correct for the test suite; a multi-worker deploy
  silently breaks all three (health 503 work shows deploy-awareness is
  growing — apply the same honesty to these stores).
- R3. Guest quota/ratelimit enforcement lives in middleware (path matching
  by string). A new route that should be guest-restricted or rate-limited
  is unrestricted by default — fail-open on future endpoints.
- R4. Claim-race test still the structural flake candidate (threading +
  SQLite); green throughout this pass, no repeat probe run this cycle.
- R5. Magic seq numbers now span 3 files (chaos, chaos-matrix, recovery
  manifest): a planner-template change will break ~10 assertions at once.

## Confidence

- **High** on the final numbers: 139 collected, 137 passed / 2 skipped /
  0 failed on the last full run, with per-file sums reconciling exactly
  (122 + 15) and both skips verified honest (no GitHub/Vultr secrets in env).
- **High** on V2-02 route coverage: every new endpoint traced from its
  `@router` decorator to at least one passing test read in full; the
  connectors gap confirmed by regex sweep over all 14 test files.
- **High** on the weak-assertion list: all 88 new V2-02 tests read in full;
  W1–W6 quote exact lines/semantics.
- **Medium** on `routes/recovery.py` internals past line 500 (endpoint
  contract + evaluator behavior verified via its 10 tests, not by reading
  every branch) and on anything landing after run 9.

## Next task

Recommended QA follow-up (ordered by risk):

1. Cover `GET /api/v1/connectors*` (list shape, per-connector health incl.
   unknown 404, resource counts after a run) — last untested route family.
2. Add the guest-mint bound tests (W5) and resume-409 detail-shape pins (W3);
   add cross-tenant 404s for resume + recovery-manifest.
3. Drive CM-14 e2e / CM-15 (MANUAL_REQUIRED/PARTIALLY_COMPENSATED) — or
   rename the misnamed store test and file the engine paths as uncovered.
4. Fill the approval/cancel/evidence/events negative matrix (410 expiry
   first — it is dead-letter code as far as tests prove).
5. Re-run the FULL suite immediately before RC tagging (R1) and confirm the
   staged-vs-unstaged commit set (I2).
