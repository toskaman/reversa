# AGENT-14 — QA Baseline (REVERSA V2 cycle 1)

## Identity

- Agent: AGENT-14, QA Engineer
- Cycle: REVERSA V2 cycle 1
- Mode: READ-ONLY (only this report file written; no source or test files touched)
- Date (UTC): 2026-11-05
- Repo root: `D:/Hackatons/Vultr`
- Suite under test: `reversa/apps/api` (pytest, `testpaths = ["tests"]`)

## Mandate

Run the FULL backend suite (pytest), report REAL results per file, check for
flaky tests, weak assertions (HTTP-only), and missing negative paths.

## Files read

Tests (all 7 files + conftest, read in full):

- `reversa/apps/api/tests/conftest.py` (fixtures: `fresh_db`, `client`, `demo_auth`, `real_auth`, `make_ready`)
- `reversa/apps/api/tests/test_api_happy.py` (1 test)
- `reversa/apps/api/tests/test_chaos.py` (2 tests)
- `reversa/apps/api/tests/test_engine_units.py` (5 tests)
- `reversa/apps/api/tests/test_planner_evidence.py` (4 tests)
- `reversa/apps/api/tests/test_security.py` (7 tests)
- `reversa/apps/api/tests/test_ai_eval.py` (2 tests)
- `reversa/apps/api/tests/test_github_contract.py` (13 tests, AGENT-05, created 15:51 during this cycle)

Source (for coverage mapping; endpoint inventory + behavior contracts):

- `reversa/apps/api/src/reversa_api/main.py`, `config.py`
- `reversa/apps/api/src/reversa_api/routes/workflows.py` (full), `chaos.py`, `evidence.py` (partial), `health.py`, `connectors.py`
- `reversa/apps/api/pyproject.toml` (pytest config)

## Files modified

- `.agents/cycles/cycle-V2-01/agent-14-qa-baseline.md` (this file) — ONLY write.

## Commands run

All from `reversa/apps/api` with `.venv\Scripts\python.exe -m pytest`
(Python 3.14.4, pytest 9.2.0):

1. `pytest tests -v` — full suite, first run.
2. `pytest tests --durations=10 -q` — full suite, second run, per-test timing.
3. `pytest tests/test_engine_units.py::test_claim_race_single_winner -q` x10 — flake probe of the 5-thread claim race.
4. `pytest test_chaos.py::test_billing_failure_compensates_everything test_engine_units.py::test_unknown_outcome_reconciles_to_failed_then_retries test_engine_units.py::test_reconcile_startup_marks_unknown -q` x3 — timing-sensitive trio repeat.
5. Same trio once more (follow-up probe after a transient collection error, see Issues).
6. All 7 test files in reverse order — isolation/order-dependence check.
7. `pytest tests --co -q` — collection count confirmation.
8. `git status --short` — workspace-dirt check (parallel agents active).

## Observed results

### Full suite: 32 passed, 2 skipped, 0 failed (3 consecutive full runs + 1 reverse-order run)

| File | Tests | Passed | Skipped | Notes |
|---|---|---|---|---|
| `test_ai_eval.py` | 2 | 1 | 1 | Vultr provider skipped honestly (no `VULTR_INFERENCE_API_KEY`/`MODEL`) |
| `test_api_happy.py` | 1 | 1 | 0 | Full onboard: intent→approve→execute→COMPLETED, 0.61 s |
| `test_chaos.py` | 2 | 2 | 0 | Billing-500 compensation slowest test, 2.10 s |
| `test_engine_units.py` | 5 | 5 | 0 | Includes thread-race + reconcile paths |
| `test_github_contract.py` | 13 | 12 | 1 | Live test skipped honestly (no token/test repo); rest offline via `httpx.MockTransport` |
| `test_planner_evidence.py` | 4 | 4 | 0 | Fast unit tests |
| `test_security.py` | 7 | 7 | 0 | Auth/isolation/approval/cancel negatives |
| **Total** | **34** | **32** | **2** | **~8.5–10 s wall time** |

- Both skips are honest `pytest.skip` / `skipif` with reasons, never faked passes.
- One standing warning (pre-existing, not from test code): `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated; install httpx2 instead` via `fastapi/testclient.py`.
- Baseline suite (excluding the new github file): 21 passed, 1 skipped. The github contract file adds 12 passed + 1 skipped.

### Flakiness probes

- `test_claim_race_single_winner` (5 threads racing one SQLite claim): **10/10 passed**, 0.34–0.50 s each. No flake observed, but it is the structurally flakiest test in the suite (thread scheduling + SQLite locking); worth keeping an eye on under CI load.
- Timing-sensitive trio (billing-failure compensation, UNKNOWN→retry, startup reconcile): **3/3 passed on repeat runs** (4.3–4.7 s per trio run).
- Reverse file order full run: **32 passed, 2 skipped** — no order dependence; `fresh_db` per-test isolation works.
- One transient anomaly: the first trio-repeat iteration printed a trailing `E SyntaxError: invalid syntax` line while parallel agents were saving files in the shared tree (`services.py` rewritten 15:52, `github.py`/`test_github_contract.py` created 15:50–15:51, uncommitted edits to `auth.py`/`workflows.py`/`services.py` per `git status`). Immediate re-run passed. Verdict: concurrent-edit collection artifact, NOT a test flake. No action for QA; noted for the record.

### Assertion-strength audit

Strong (state + content, not just HTTP):

- Happy path asserts workflow state, per-action states, exact resource counts across 5 service/kind pairs, evidence-chain validity, CLI `verify_bundle`, and HTML export content.
- Chaos asserts terminal `COMPENSATED`, exact per-seq state map, exact reverse compensation order `[8,7,5,4,3,2,1]`, and physical resource restoration (workspace gone, users/org archived).
- Idempotence asserts `replay` flag flip plus exact resource count (no duplicate effects).
- Evidence asserts chain valid → tamper → invalid at exact `bad_seq == 2`, plus secret redaction in stored payload.
- AI eval asserts measured rates (100% schema-valid, 0% refusal documented as limitation).

Weak / HTTP-only / misleading (details in Issues):

1. `test_concurrent_modification_blocks_compensation` — **name overclaims**: it only checks `DemoStore.set_status` raises `PreconditionFailed` on version conflict. It never touches compensation and never exercises any `MANUAL_REQUIRED` path. The engine-level unsafe-compensation path is effectively untested despite the name/docstring.
2. `test_offline_labels_add_and_remove` — disjunctive assert (`"bug" in removed or "reversa" in removed`) accepts two different outcomes; should pin the exact expected label set.
3. `test_no_token_rejected` / `test_bad_token_rejected` / `test_chaos_forbidden_for_real_tenant` — status-code-only. Acceptable for auth guards, but none checks the error-body shape (`code`/`message` contract).
4. `test_create_is_approval_gated_and_honest` — string-fragility: `"delete" not in NOTE.replace("cannot be deleted", "")` passes/fails on prose wording rather than a structured honesty flag. Works, but brittle.
5. Chaos per-seq map (`by_seq[6] == FAILED`, exact comp order) is strong but **brittle to planner-template changes**: any step insert/reorder in the deterministic template breaks magic numbers without a behavior regression.

## Tests (what exists, per file)

- `test_api_happy.py`: 1 end-to-end (intent→approve→preview→execute→evidence JSON+HTML).
- `test_chaos.py`: billing-500 full-compensation E2E; store-level version-conflict unit check (misnamed, see above).
- `test_engine_units.py`: illegal transitions; 5-thread claim race; double-execute idempotence; startup reconcile → UNKNOWN; timeout → UNKNOWN → reconcile → retry → COMPLETED.
- `test_planner_evidence.py`: 10-step deterministic plan valid; validator rejects unknown action + bad deps; chain append/verify/tamper/redact; nested redact.
- `test_security.py`: no-token 401/403; bad-token 403; cross-tenant workflow invisible (GET + execute); chaos forbidden for real tenant; wrong-hash approve 409 + stays AWAITING; execute-before-approve 409; cancel READY → CANCELLED + execute-after-cancel 409.
- `test_ai_eval.py`: deterministic baseline measured on 10 cases; Vultr provider live eval (honest skip).
- `test_github_contract.py`: 7 contract-shape/precondition/token offline checks; 5 MockTransport offline execute/verify/compensate cycles; 1 live cycle (honest skip).

## Issues

### I1. Untested routes (no test hits these endpoints at all)

- `GET /health`, `/healthz`, `/readyz`, `/api/v1/health` — zero coverage. Note `/readyz` returns 200 even when degraded (same body as `/health`); untested either way.
- `GET /api/v1/connectors`, `GET /api/v1/connectors/{id}/health` — zero coverage (incl. unknown-connector 404).
- `GET /api/v1/demo/chaos` (list rules) and `DELETE /api/v1/demo/chaos/{rule_id}` — only POST is tested.
- `GET /api/v1/me` — zero coverage.
- `GET /api/v1/workflows/{id}/events/stream` (SSE, 120 s idle loop, `?token=` query-param auth, `Last-Event-ID` resume, cross-tenant error event) — entirely untested; highest-risk untested surface (auth via query param + long-lived streaming + per-iteration sessions).

### I2. Missing negative paths on tested routes

- Chaos POST: unknown fault → 422, unknown connector → 422, chaos with `REVERSA_CHAOS=0` → 403, list/delete as real tenant → 403, delete nonexistent/foreign rule → 404. None tested.
- Intents POST: empty/missing intent → 422, `use_ai=true` without Vultr config (fallback or 500? behavior unpinned). None tested.
- Approve: double approve → 409, approve non-AWAITING → 409, expired approval → 410 (30-min expiry path dead code as far as tests prove), malformed body → 422, cross-tenant approve → 404. Only wrong-hash tested.
- Execute: nonexistent workflow → 404, re-execute after COMPENSATED (replay? only COMPLETED replay tested), concurrent double-execute race on `execute_key` (only sequential tested).
- Cancel: cancel COMPLETED/CANCELLED → 409, cancel nonexistent → 404, cross-tenant cancel → 404, cancel AWAITING_APPROVAL (allowed? unpinned).
- Evidence: `format=xml`/unknown (silently returns JSON — unpinned), cross-tenant → 404, nonexistent → 404.
- Events: `since_seq`/`limit` params, cross-tenant → 404.
- Preview: cross-tenant → 404 (only happy-path owner access tested).
- List workflows: `limit`/`cursor` pagination untested.
- Auth: malformed `Authorization` scheme (no `Bearer` prefix), empty Bearer [REDACTED] untested (only missing + unknown-token covered).

### I3. Engine paths with no coverage despite suggestive names

- `MANUAL_REQUIRED` / unsafe-compensation path: nothing drives the engine into it (see weak-assertion item 1).
- Reconcile-when-present: only the absent-resource retry path is tested; UNKNOWN where the resource already exists (verify-true path) is not.
- Real-tenant (non-demo) full execute: every execute test uses `demo_auth`; non-demo onboarding is untested.
- `verify_bundle` CLI: only the valid-bundle path (via happy path); invalid/tampered bundle CLI output untested.

### I4. Non-test observations (seen during QA, owned by others)

- `git status` shows uncommitted edits to `auth.py`, `connectors/services.py`, `routes/workflows.py` plus new `connectors/github.py` — all mid-flight V2 cycle-1 work; baseline numbers above are against this dirty tree.
- `.agents/cycles/cycle-V2-01/` already contains agent-01, 02, 07, 09, 10, 11 reports; no conflicts with this file.

## Risks

- R1. SSE stream (`events/stream`) ships with query-param auth and zero tests — the single biggest QA blind spot; a token-leak-via-logs or cross-tenant leak here would be silent.
- R2. Chaos list/delete untested while chaos POST is load-bearing in E2E tests — rule lifecycle (stale rules leaking across runs) is unverified; currently masked by per-test `fresh_db` isolation.
- R3. Approval-expiry (410) and MANUAL_REQUIRED paths are dead-letter code paths: implemented but unreachable in tests, so regressions will not trip the suite.
- R4. Claim-race test is timing/threading-sensitive by construction; 10/10 green locally, but it is the first candidate to flake on a loaded CI runner.
- R5. Magic seq numbers in chaos assertions (`by_seq[6]`, comp order list) will false-fail on any planner-template change — maintenance cost, not a correctness signal.

## Confidence

- **High** that the reported numbers are real: 34 collected (collection listing captured), 32 passed / 2 skipped on 4 independent full runs (2 forward, 1 with durations, 1 reverse order), plus 10x race and 4x trio repeats. All commands and outputs observed in-session.
- **High** on the untested-routes list: derived from a regex sweep of all `@router/@app` decorators cross-checked against every test file read in full.
- **Medium** on the transient SyntaxError attribution (concurrent-edit artifact): consistent with observed parallel-agent writes and immediate green re-run, but the failing output was not captured in full.

## Next task

Recommended QA follow-up for cycle 2 (ordered by risk):

1. Add SSE stream tests (auth via `?token=`, bad token, cross-tenant, done-event on terminal workflow) — covers R1.
2. Add route-negative tests: chaos 422/403/404 matrix, approve 409/410/422 matrix, evidence/events/preview cross-tenant 404s, health + connectors + `/me` smoke tests — covers I1/I2.
3. Rename or upgrade `test_concurrent_modification_blocks_compensation` to actually drive the engine MANUAL_REQUIRED path (or rename to `test_store_version_conflict` and file the engine path as uncovered) — covers I3.
4. Pin the label-compensation assertion to an exact set and add error-body shape asserts to the three auth-guard tests — fixes weak items 2–3.
