# AGENT-14 — QA, REVERSA V2 cycle 3

## Identity

- Agent: AGENT-14, QA Engineer
- Cycle: REVERSA V2 cycle 3
- Mode: READ-ONLY (only this report file written; no source or test files touched)
- Date (UTC): 2026-11-05
- Repo root: `D:/Hackatons/Vultr`
- Suite under test: `reversa/apps/api` (pytest, `testpaths = ["tests"]`)
- Observation window: V2-03 backend work landed continuously during this QA
  pass (143 → 200 passed across runs). Every count below is tied to the
  run that produced it; the FINAL verdict is run 5.

## Mandate

Run the FULL backend suite, collect per-file results, audit weak
assertions among V2-03 additions. Read files before citing. Never invent
results. Never commit secrets. Do not push.

## Files read

V2-03 additions — all read in full (new files) or via complete `HEAD` diff:

- `tests/test_connectors_routes.py` (NEW, 6 tests, full read)
- `tests/test_negative_matrix.py` (NEW, 30 tests, full read)
- `tests/test_guest_sessions.py` (+11 c3 tests, full diff read + head re-read
  for fixtures/helpers)
- `tests/test_perf_regressions.py` (+1 F4 test, full diff read + `_Counter`
  head re-read)
- `tests/test_ai_eval.py` (10→30 casebook + 4 new tests, full diff read)
- `tests/test_engine_units.py` (+2 F3 tests, full diff read)
- `tests/test_chaos_matrix.py` (+3 CM-11/13/15 tests, full diff read)
- `src/reversa_api/ratelimit.py` (full diff: window cap, slash norm,
  fail-open, clamp, Retry-After)
- `src/reversa_api/engine/saga.py` (full diff: F3 chaos filter-before-pick)
- `src/reversa_api/evidence.py` + `routes/evidence.py` (full diffs: F4
  `verify_chain_rows` single pass)
- `src/reversa_api/cli.py` (full diff: docstring + `…`→`...` message text)
- `.github/workflows/ci.yml` (full diff: docker jobs + secrets-scan)
- `routes/connectors.py` (full, for endpoint-contract verification)
- `tests/conftest.py` (full, fixtures)
- Prior: `.agents/cycles/cycle-V2-02/agent-14-qa-v202.md`

Behavior-contract spot checks via search (all confirmed in source):

- `GuestMintIn` bounds `ge=1, le=20/50` (`routes/guest_sessions.py:35-39`,
  limits in `auth.py:137-138`) — matches c3 bound tests exactly
- Resume/approve detail strings (`workflows.py:168,182,224`) — match
  negative-matrix pins
- CLI head-mismatch pinned by substring only
  (`test_cli_verify.py:126-127`: `"head hash"`, `"trailing truncation"`)
  — the `…`→`...` change is unpinned either way, no test impact

## Files modified

- `.agents/cycles/cycle-V2-03/agent-14-qa-v203.md` (this file) — ONLY write.

## Commands run

All with `reversa/apps/api/.venv/Scripts/python.exe -m pytest`.
Tree was churning (parallel agents); each run is a timestamped sample:

1. `pytest tests -q --tb=short` → **143 passed, 2 skipped** (40.30 s).
   Tree then: committed V2-02 base, no V2-03 landings yet.
2. Per-file loop (`pytest tests/<file> -q --tb=no`, 14 files) → sum
   **154 passed, 2 skipped**. Guest c3 tests (+11) landed mid-window.
3. `pytest tests -q --tb=short` → **197 passed, 2 skipped** (54.75 s).
   Connectors (6) + negative matrix (30) + perf F4 (1) + ai-eval (4) +
   engine F3 (2) landed.
4. Per-file loop (16 files) → **200 passed, 2 skipped**. Chaos CM-11/13/15
   (+3) landed mid-loop; the loop's `test_chaos_matrix` run (8 passed)
   already included them.
5. FINAL `pytest tests -q --tb=short` → **200 passed, 2 skipped** (49.58 s).
   202 collected = 143 base + 57 V2-03. **Zero failures. Verdict run.**
6. `pytest tests/test_ai_eval.py tests/test_github_contract.py -q -rs` →
   **46 passed, 2 skipped** (0.10 s); both skips confirmed honest
   (Vultr not configured; no GitHub token/repo).

Plus: `git status`/`git diff HEAD` snapshots (api scope), `rg` sweeps for
detail-string and bound verification. No secrets in env needed checking
beyond the two honest skips (skip reasons name the missing config).

## Observed results

### Final suite: 200 passed, 2 skipped, 0 failed (run 5)

| File | Tests | Passed | Skipped | Delta vs V2-02 base |
|---|---|---|---|---|
| `test_ai_eval.py` | 12 | 11 | 1 | +4 (30-case book, 3 offline fakes) |
| `test_api_happy.py` | 1 | 1 | 0 | — |
| `test_chaos.py` | 4 | 4 | 0 | — |
| `test_chaos_matrix.py` | 8 | 8 | 0 | +3 (CM-11/13/15) |
| `test_cli_verify.py` | 14 | 14 | 0 | — |
| `test_connectors_routes.py` | 6 | 6 | 0 | NEW (connectors routes) |
| `test_demo_isolation.py` | 3 | 3 | 0 | — |
| `test_engine_units.py` | 20 | 20 | 0 | +2 (F3 precedence) |
| `test_github_contract.py` | 36 | 35 | 1 | — |
| `test_guest_sessions.py` | 23 | 23 | 0 | +11 (c3 rate/quota edges) |
| `test_health.py` | 5 | 5 | 0 | — |
| `test_negative_matrix.py` | 30 | 30 | 0 | NEW (approve/cancel/resume/evidence/guest) |
| `test_perf_regressions.py` | 4 | 4 | 0 | +1 (F4 single-pass) |
| `test_planner_evidence.py` | 5 | 5 | 0 | — |
| `test_recovery_manifest.py` | 10 | 10 | 0 | — |
| `test_security.py` | 21 | 21 | 0 | — |
| **Total** | **202** | **200** | **2** | **+57 tests vs base (143→200)** |

- Per-file sums reconcile exactly with the final full run (200 + 2).
- Both skips are the pre-existing honest ones (same files, same reasons
  as V2-02). No new skips.
- Standing warning unchanged (pre-existing Starlette/httpx deprecation).
- V2-03 src additions observed in tree: ratelimit hardening (window cap
  10k + purge-then-evict, trailing-slash tier norm, unknown-tier
  fail-open, degenerate clamp, positive-int Retry-After), F3 chaos
  filter-before-pick in `_consume_chaos`, F4 `verify_chain_rows`
  single-pass evidence export, CLI docstring/ellipsis cosmetic, CI docker
  jobs + secrets-scan. Web + docs changes noted, out of backend scope.

### V2-03 assertion quality: strong, 12 new minor weaks (none blocking)

Strong (exact states/codes/counts/payloads): connectors exact entry key
sets + store strings + cross-tenant zero-resources on both endpoints;
negative-matrix exact detail pins (`workflow not found`, `plan changed`,
`nothing to approve`, 410→409 expiry consumption + `approval.expired`
event, `already COMPLETED/CANCELLED`, `compensation in progress`,
`in flight` + seq, `only interrupted`, `nothing to resume`,
`QUOTA_EXHAUSTED` codes); c3 exact tier map + fail-open tuple + full
rollover cycle + eviction counts + Retry-After>=1 over HTTP + mint
bounds matrix (0/21/0/51/negatives rejected, 20/50 accepted) + sibling
quota isolation; F4 tuple-equivalence incl. tamper + `== 1` statement
locks on json+html + CLI `verify_bundle`; ai-eval full-category refusal
pins + per-injection schema/tool-precision pins + error-count equality;
F3 exact fault codes both directions + two-sided budget asserts; CM
terminal states + transition trails + `chaos.injected` payloads + budget
via API + resource counts + chain-valid.

New weak assertions among V2-03 additions (all minor):

1. W-C1 `test_list_connectors_shape:37` — bare `len(capabilities) > 0`;
   no count pin.
2. W-C2 same test, line 30 — subset assert: an unexpected extra
   connector would pass silently (documented: github registers when
   configured).
3. W-C3 `test_health_each_registered_connector` — health body keys not
   pinned as an exact set (4 individual asserts only). Loop-guarded
   correctly (`len(REGISTRY) >=` first), so no vacuous-pass risk.
4. W-N1 negative matrix — ~17 status-only 401/404/409 asserts
   (cross-tenant/anonymous guards; resume AWAITING/CANCELLED 409s).
   Consistent with suite style for guards; note resume READY/COMPLETED
   409s DO pin details, closing V2-02 W3 for those two paths.
5. W-N2 `test_evidence_unknown_format_falls_back_to_json` — documents a
   silent-JSON fallback for unknown `format` instead of a 422. Honest
   comment; the smell is in the behavior, not the test.
6. W-G1 `test_c3_check_degenerate_config_clamped` — `retry >= 0.0` is
   near-vacuous.
7. W-G2 `test_c3_window_store_bounded_oldest_evicted` — `<= 4` where
   exact `== 4` (cap 3 + 1 insert) is expected.
8. W-G3 c3 limiter tests — white-box on privates (`_tier_for`,
   `_check`, `_WINDOWS`, `_MAX_WINDOWS`); refactor-coupled, mitigated
   by one HTTP-level test. Same note for the F3 `_consume_chaos` units
   (mitigated by CM-11 e2e) and `_GUEST_SESSIONS` poking in expiry
   tests (no time-travel seam).
9. W-A1 ai-eval fakes look up the case CATEGORY by exact intent string —
   the fakes see the answer key, so "discriminates" proves eval-harness
   plumbing (mutation-style), not planner judgment. Valid self-test,
   overstated docstring noun ("prove the eval itself discriminates").
10. W-A2 `test_eval_casebook_shape` — category superset (`<=`): an
    unknown 7th category would pass.
11. W-M1 CM-11 — `len(waits) >= 1` where single-shot implies exactly 1.
12. W-M2 CM-11/13/15 inherit magic-seq brittleness (seqs 2/6/9/10, action
    names); extends standing risk R5 to a 4th file.

V2-02 W5 (mint bounds untested) is now CLOSED by c3 tests; V2-02 W3
partly closed (resume READY/COMPLETED detail pins added); W1/W2/W4/W6
untouched (files unchanged).

### Untested surface among V2-03 src additions: NONE

Every V2-03 backend src change has at least one test read in full:
ratelimit hardening → 11 c3 tests; F3 → 2 engine units + CM-11 e2e;
F4 → perf equivalence + statement-lock test; CLI text → existing
substring pins (14/14 green).

Remaining untested surface (updated for cycle-4 planning):

- `GET /api/v1/connectors*` gap from V2-02 is CLOSED (6 tests). No
  fully-untested route family remains.
- Chaos-matrix spec: CM-11/13/15 now covered (13/20 per file header).
  Still MISSING: CM-06, CM-07, CM-12, CM-14 (e2e), CM-16, CM-17, CM-18.
- Negative matrix closed approve/cancel/resume/evidence/guest; still
  open: intents 422s (empty intent, `use_ai=true` unconfigured),
  events `since_seq`/cross-tenant, preview cross-tenant, list
  `cursor`/page-2, chaos `REVERSA_CHAOS=0` 403 + real-tenant guards,
  stream `Last-Event-ID` resume, recovery-manifest cross-tenant 404.

## Tests (what exists)

- V2-02 base (143): unchanged files all green, counts identical.
- V2-03 new (57): connectors routes (6), negative matrix (30:
  approve 7, cancel 7, resume 7, evidence 4, guest 5), guest c3
  rate/quota edges (11), perf F4 (1), ai-eval casebook+fakes (4),
  engine F3 (2), chaos CM-11/13/15 (3).

## Issues

- I1 (observation, not mine to fix): `test_cli_verify.py` pins the
  strict head-mismatch message by substring only, so the V2-03
  `…`→`...` text change was unverifiable by the suite either way.
  Cosmetic; no action unless exact-message pinning is adopted.
- I2 (spec smell, not a bug): unknown evidence `format` silently
  returns JSON (W-N2). If 422 is the intended contract, file it.
- I3: CM-13's mid-run `_consume_chaos` monkeypatch and CM-15's
  DB-seeded custom plan are invasive techniques, both justified in
  docstrings. No action; noted for future maintainers.

## Risks

- R1. Tree churn (carried): +57 tests and 5 src diffs landed DURING
  this pass. Counts are correct as of run 5; anything landing after
  needs a fresh `pytest` before tagging.
- R2. Magic seq/action-name coupling now spans 4 test files
  (chaos, chaos-matrix, recovery manifest, + CM-11/13/15 pins):
  a planner-template change breaks ~15 assertions at once.
- R3. (Carried, unchanged) In-memory stores (SSE tickets, guests, rate
  windows) are single-process; the new 10k window cap bounds memory
  but multi-worker deploy still silently fragments all three.
- R4. (Carried) Guest/ratelimit enforcement is middleware path-match
  (fail-open on future endpoints); the trailing-slash norm closes one
  bypass class, not the structural one.
- R5. (Carried) Claim-race threading test still the structural flake
  candidate; green throughout, no repeat probe this cycle.

## Confidence

- **High** on the final numbers: 202 collected, 200 passed / 2 skipped
  / 0 failed, per-file sums reconciling exactly, both skips verified
  honest with reasons quoted from the runner.
- **High** on V2-03 coverage: all 57 new tests read in full (2 new
  files) or via complete diff (5 grown files); every V2-03 src hunk
  traced to at least one passing test.
- **High** on the weak-assertion list: W-C1–W-M2 quote exact
  lines/semantics; all are minor, none block.
- **Medium** on anything landing after run 5 (sibling agents still
  active: web, docs, CHANGELOG, cycle-03 reports).

## Next task

Recommended QA follow-up (ordered by risk):

1. Re-run the FULL suite immediately before tagging (R1) — the tree
   was still churning at run 5.
2. File-or-fix the unknown-evidence-format fallback (I2/W-N2).
3. Pin `len(waits) == 1` (W-M1), eviction `== 4` (W-G2), and resume
   AWAITING/CANCELLED 409 details (W-N1 remainder) — five-line
   hardening.
4. Drive CM-14 e2e / CM-06/07/12/16/17/18, or record them as accepted
   gaps; rename-or-cover the misnamed store-level test per V2-02
   follow-up #3 (still open).
5. Fill the intents/events/preview/list/chaos/stream negative
   remainder listed above.
