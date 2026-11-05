# AGENT-14 — QA, REVERSA V2 cycle 4 (FINAL ASCENT)

## Identity

- Agent: AGENT-14, QA Engineer
- Cycle: REVERSA V2 cycle 4 (FINAL ASCENT)
- Mode: READ-ONLY (only this report file written; no source or test files touched)
- Date (UTC): 2026-11-05
- Repo root: `D:/Hackatons/Vultr`
- Suite under test: `reversa/apps/api` (pytest, `testpaths = ["tests"]`)
- Observation window: tree churned during this pass. Run 1 hit the clean
  committed V2-03 base (204/2, matches merge commit claim); run 2 hit a
  mid-churn V2-04 tree (251 passed + 3 failed + 2 skipped). Every count
  below is tied to the run that produced it.

## Mandate

Run the FULL backend suite + per-file counts; start a LOCAL stack and run
the browser smoke for guest journey if feasible, else mark honestly.
READ-ONLY except this file with real counts. Never invent results. Never
commit secrets. Do not push. Localhost probes only (no prod/SSH).

## Files read

Committed-base context (all read before citing):

- `.agents/cycles/cycle-V2-03/agent-14-qa-v203.md` (full — prior counts,
  weak-assertion list W-C1–W-M2, open gaps)
- `tests/conftest.py` (full — fixtures, `make_ready` journey shape)
- `src/reversa_api/config.py` (full — env settings, sqlite data dir)
- `src/reversa_api/routes/guest_sessions.py` (lines 1–80 — mint contract)
- `src/reversa_api/cli.py` (V2-03 `3fad9e4..HEAD` diff + `main` tail
  lines 180–205 — malformed/garbage handling)
- `src/reversa_api/connectors/github.py` + `sdk.py` +
  `evidence.py` (V2-03 diffs — 404-sniff fix, `status_code` plumbing,
  `verify_chain_rows`)
- `src/reversa_api/routes/workflows.py` + `auth.py` (targeted search:
  endpoint list, quota 410 contract, demo seed)
- `tests/test_cli_verify.py` + `tests/test_github_contract.py` (V2-03
  diffs — the 4 tests that landed after QA run 5)
- `reversa/apps/web/lib/api.ts` (lines 1–60 — API base/token wiring),
  `reversa/apps/web/package.json`, `app/` route listing

V2-04 churn (dirty tree at run 2, read to diagnose the 3 failures):

- `git diff` of `routes/evidence.py` (full V2-04 hunk — 422 format gate)
- `git diff` of `auth.py` (AGENT-07 per-session isolation header +
  `_sweep_guest_org` hunk, first ~90 lines)
- `tests/test_guest_isolation.py` (header + fixture, first 40 lines)
- `tests/test_crash_recovery.py` (header + seed helpers, first 30 lines)
- `git show --stat f777543`, `git diff --stat` (churn characterization)

Sibling V2-04 reports (`agent-01/-02/-05/-08/-09`) were listed, not read
(outside this mandate; no claim in this report depends on them).

## Files modified

- `.agents/cycles/cycle-V2-04/agent-14-qa-v204.md` (this file) — ONLY write.
- Throwaway probe artifacts under `%TEMP%/reversa-qa-v204/` (server logs,
  guest-probe script, evidence bundle) — outside the repo, contain a
  throwaway local demo token, never committed. No token is quoted anywhere
  in this report.

## Commands run

All pytest via `reversa/apps/api/.venv/Scripts/python.exe -m pytest`
(Python 3.14.4, pytest 9.2.0):

1. `pytest tests -q --tb=short` on the CLEAN base → **204 passed,
   2 skipped** (54.33 s). Matches merge commit `f777543` "204 green".
2. Per-file loop, 16 files, clean base → each file green; sums **204
   passed, 2 skipped**, reconciling exactly with run 1.
3. `pytest test_ai_eval.py -q -rs` + `pytest test_cli_verify.py
   test_github_contract.py -q -rs` → both skips confirmed honest
   (`test_ai_eval.py:189` vultr unconfigured; `test_github_contract.py:517`
   no GitHub token/repo). `test_cli_verify.py --collect-only` → 17 tests.
4. Local API stack: `uvicorn reversa_api.main:app --host 127.0.0.1
   --port 8099` with `REVERSA_DATA_DIR` under `%TEMP%` (PID 20504,
   started by me, stopped after; verified down). Guest-journey probe
   script + follow-up execute/evidence probes (all localhost).
5. `python -m reversa_api.cli verify %TEMP%/reversa-qa-v204/bundle.json`
   on the smoke-exported bundle → `VALID: offline chain valid
   (59 events recomputed)`, exit 0.
6. Web serving probes against the pre-existing local `next start -p 3100`
   (PID 6156, NOT mine — probed read-only, left running): `/`,
   `/command`, `/connectors`, `/recovery`, `/recovery-race`, `/roi`,
   `/settings`, `/demo-lab`, `/time-machine`, `/workflows/1`,
   `/evidence/1` → all HTTP 200. Bare `/workflows` and `/evidence`
   404, which is EXPECTED (dynamic `[id]`-only routes, verified in
   `app/workflows/[id]/page.tsx`, `app/evidence/[id]/page.tsx`).
7. `pytest tests -q --tb=short` on the CHURNED tree → **3 failed,
   251 passed, 2 skipped** (78.74 s). Targeted re-run of the 3 failures
   with `--tb=long` for exact tracebacks.
8. Per-file loop, 18 files (incl. 2 new), churned tree → sums **251
   passed, 3 failed, 2 skipped**, reconciling exactly with run 7.
9. `git status`/`git diff` snapshots throughout; `rg` sweeps for
   contracts. `Stop-Process` on my own API server only.

## Observed results

### Run 1 — committed V2-03 base: 204 passed, 2 skipped, 0 failed

| File | Passed | Skipped | Delta vs QA-v203 run 5 (200/2) |
|---|---|---|---|
| `test_ai_eval.py` | 11 | 1 | — |
| `test_api_happy.py` | 1 | 0 | — |
| `test_chaos.py` | 4 | 0 | — |
| `test_chaos_matrix.py` | 8 | 0 | — |
| `test_cli_verify.py` | 17 | 0 | **+3** (landed post-QA-run-5) |
| `test_connectors_routes.py` | 6 | 0 | — |
| `test_demo_isolation.py` | 3 | 0 | — |
| `test_engine_units.py` | 20 | 0 | — |
| `test_github_contract.py` | 36 | 1 | **+1** (landed post-QA-run-5) |
| `test_guest_sessions.py` | 23 | 0 | — |
| `test_health.py` | 5 | 0 | — |
| `test_negative_matrix.py` | 30 | 0 | — |
| `test_perf_regressions.py` | 4 | 0 | — |
| `test_planner_evidence.py` | 5 | 0 | — |
| `test_recovery_manifest.py` | 10 | 0 | — |
| `test_security.py` | 21 | 0 | — |
| **Total** | **204** | **2** | **+4, all in merge `f777543`** |

The +4 (all read in full via diff, all strong pins):

- `test_malformed_bundle_is_invalid_not_crash` — 8 malformed shapes →
  `ok is False` + `"malformed"` in message. Covers `cli.py` V3-3 guards.
- `test_empty_bundle_stays_documented_valid` — exact message pin,
  honestly documents the 0-event blind spot.
- `test_main_malformed_file_and_garbage_is_invalid` — exit 1 + `INVALID`
  for missing-key file, garbage JSON, missing file. Covers `main()`'s
  `(OSError, ValueError, UnicodeDecodeError)` handler (`cli.py:188-193`,
  read).
- `test_verify_403_mentioning_404_still_raises` — 403-with-"404"-body
  raises `GITHUB_API_ERROR` (no longer misread as absence). Covers
  `github.py` V3-1 structured-status check. Minor note: pins `code` but
  not the new `exc.status_code == 403` passthrough itself (new weak W-V41,
  trivial).

Standing warning unchanged (pre-existing Starlette/httpx deprecation).

### Run 2 — churned V2-04 tree: 251 passed, 3 failed, 2 skipped

256 collected (+50 vs base). Per-file (only deltas shown; all other files
identical to run 1):

| File | Result | Delta vs base |
|---|---|---|
| `test_chaos_matrix.py` | 15 passed | +7 |
| `test_crash_recovery.py` | 13 passed | NEW |
| `test_engine_units.py` | 22 passed | +2 |
| `test_guest_isolation.py` | 17 passed | NEW (AGENT-07) |
| `test_guest_sessions.py` | 21 passed, **2 failed** | same count, 2 stale (F1, F2) |
| `test_negative_matrix.py` | 29 passed, **1 failed** | same count, 1 stale (F3) |
| `test_recovery_manifest.py` | 18 passed | +8 |
| `test_security.py` | 24 passed | +3 |

Dirty-tree scope at run 2: 19 modified files (`auth.py`, `saga.py`,
`routes/evidence|guest_sessions|recovery|workflows.py`, 4 test files,
web components, `RUNBOOK.md`, demo script) + 4 untracked
(`test_crash_recovery.py`, `test_guest_isolation.py`,
`ManifestPanel.tsx`, `cycle-V2-04/`). None of it is mine.

### Local-stack guest journey smoke: FULLY GREEN (HTTP-level)

Ran mid-churn on `127.0.0.1:8099` (real uvicorn, fresh temp sqlite):

- `GET /api/v1/health` → `{"status":"ok","version":"0.1.0","db":true}`;
  `GET /health` → 200
- Owner mints guest (quotas 2 wf / 5 ex echoed, `expires_at` +60 min)
- Guest `POST /intents` → 201 `AWAITING_APPROVAL` → approve → `READY` →
  `POST /execute` → **`COMPLETED` in 0.2 s** → evidence export 28 208 B,
  59 events → CLI offline verify **VALID (59 recomputed), exit 0**
- Guards: guest-cannot-mint → 403; anonymous intent → 401; 3rd workflow
  over quota-2 → 410 (matches `auth.py:397-398` "Raise 410" contract);
  fresh guest reading another session's workflow → 404
- The cross-guest 404 proves the server was already running AGENT-07's
  NEW per-session isolation semantics (old code returned 200 for
  same-org reads per the now-failing F2 test). So the smoke
  inadvertently validated the NEW contract end-to-end. Green either way.

### Browser smoke: NOT FEASIBLE here — marked honestly

No browser automation exists in this environment (no Playwright/Selenium
tool; the granted tools are file/shell probes only). What was done
instead: serving smoke of the pre-existing local production web build
(`next start`, PID 6156, not mine) — 11/11 routes HTTP 200, correct
`<title>REVERSA — Self-Healing AI Operations</title>`. A true
browser-driven guest journey (click mint → paste credential → run
workflow in UI) was NOT executed and is NOT claimed.

## Tests (what exists)

- Committed base (204 + 2 honest skips): unchanged files all green with
  counts identical to merge claim; the 4 post-QA-run-5 tests audited
  above (strong, +1 trivial weak W-V41).
- V2-04 churn (+50 collected): crash-recovery boundaries (13),
  per-session guest isolation incl. PUBLIC mint (17), chaos matrix +7,
  recovery manifest +8, engine +2, security +3. New files' headers read;
  full assertion audit deferred to the V2-04 close-out pass once the
  tree settles (out of scope for this red-tree sample).
- V2-03 follow-up status: unknown-evidence-format fallback (I2/W-N2) is
  now FIXED in behavior (422 gate) — but its old test is the stale F3.
  W-M1/W-G2/W-N1-remainder hardening, CM-14 e2e, and the negative
  remainder list are untouched by this churn (files changed but those
  pins not observed altered — not re-audited line-by-line on the red
  tree).

## Issues

- **F1 `test_guest_sessions.py:50 test_owner_can_mint_guest_session`** —
  `me["org_slug"]` is now `'guest-<session>'`, test expects the parent
  demo slug. Cause: intentional AGENT-07 per-session ephemeral-org
  change. Stale test, not a regression. Owner: whoever owns the guest
  tests (AGENT-07 or guest-test owner) must update the pin.
- **F2 `test_guest_sessions.py:134
  test_guest_demo_org_only_isolation`** — guest reading the OWNER's demo
  workflow is now 404 (was 200). Same intentional cause; the old
  "guest sees demo org" contract is dead by design (12 new A/B isolation
  checks in `test_guest_isolation.py` pin the new contract). Stale test.
- **F3 `test_negative_matrix.py:305
  test_evidence_unknown_format_falls_back_to_json`** — `?format=xml` now
  422 with `unsupported format 'xml'; use 'json' or 'html'`
  (`routes/evidence.py` V2-04 hunk, read in full). Intentional fix of
  V2-03 I2. Stale test: rename + flip to pin 422 and the exact detail.
- **W-V41 (new, trivial)** — `test_verify_403_mentioning_404_still_raises`
  pins `code` but not `exc.status_code`; the `sdk.py` passthrough has no
  direct pin. One-line assert.
- **Process note** — a production web build (`next start -p 3100`,
  PID 6156) is running from this repo, started outside this QA pass. I
  probed it read-only and left it alone; its owner should confirm it is
  intentional.

## Risks

- **R1. Suite is RED at report time (carried, now realized):** 3 stale
  tests vs intentional V2-04 behavior changes. Nothing may be tagged
  until F1–F3 are updated and a settled-tree full run is green. The
  churn rate (19 modified + 4 untracked mid-pass) means any count in
  this report is already a sample, not a verdict on HEAD.
- **R2. Smoke ran mid-churn:** the local-stack journey is dated to the
  tree state at server start (~16:2x UTC); behaviorally it ran the NEW
  guest semantics, but it is not a clean-base reproduction. Re-run the
  journey once after the tree settles if a release note depends on it.
- **R3. (Carried)** Magic seq/action-name coupling, single-process
  in-memory stores (guests/rate windows/SSE), middleware path-match
  enforcement, claim-race flake candidacy — all still open per v203;
  not re-probed this cycle.
- **R4. No browser-driven coverage exists anywhere in this pipeline:**
  the guest journey has HTTP-level proof only. If jury demo flows depend
  on UI behavior, that is an untested surface by construction.

## Confidence

- **High** on run 1: 206 collected, 204/2/0, per-file sums reconciling
  exactly, both skips quoted with reasons, +4 traced to exact tests.
- **High** on run 2 numbers and the F1–F3 diagnoses: full tracebacks
  captured, each failure traced to its intentional source hunk, per-file
  sums reconciling exactly (251 + 3 + 2 = 256).
- **High** on the HTTP guest-journey smoke: every step quoted with real
  statuses/payloads, plus CLI cross-verification of the exported chain.
- **High (honest negative)** on browser smoke: not feasible with granted
  tools; serving smoke only, no UI interaction claimed.
- **Low** on anything landing after run 2 — siblings were actively
  committing during this pass.

## Next task

Ordered QA follow-up for V2-04 close-out:

1. Update the 3 stale tests (F1/F2 guest pins, F3→422 pin) and re-run
   the FULL suite on a settled tree — the release gate.
2. Full assertion audit of the +50 new tests (crash 13, isolation 17,
   chaos +7, manifest +8, engine +2, security +3) once green.
3. Add the one-line `status_code` pin (W-V41) and the v203 remainder
   (W-M1, W-G2, resume AWAITING/CANCELLED details).
4. Re-run the localhost guest journey post-settle if release notes cite it.
5. Decide whether browser-driven coverage (Playwright or manual jury
   script) is in scope before tag; currently the pipeline has none.
