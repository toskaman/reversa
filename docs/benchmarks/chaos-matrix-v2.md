# Chaos Matrix V2 — 20-scenario critical matrix (REVERSA V2 cycle 1, §9)

Owner: AGENT-13 (Chaos Engineer). Date: 2026-11-05. Status: design only, no code changed.

Scope: chaos routes (`POST/GET/DELETE /api/v1/demo/chaos`), the engine fault path
(`_consume_chaos` → `chaos_error`), Chaos Lab UI (`/demo-lab`), and all existing
chaos-adjacent tests. Each scenario maps to an EXISTING test (file + name cited)
or is marked MISSING (to be implemented in a later cycle).

Note: no `§9` spec document was found in the repo (`docs/superpowers/specs` is
empty); this matrix is designed from the inspected code and the cycle-1 mandate.

## Ground truth (inspected)

- Faults: `http500` (retryable), `http429` (retryable), `timeout`
  (retryable + uncertain → `UNKNOWN_OUTCOME`), `malformed` (non-retryable),
  `latency` (sleeps 2 s, no error), `crash` (retryable + uncertain) —
  `reversa/apps/api/src/reversa_api/connectors/sdk.py` (`CHAOS_FAULTS`, `chaos_error`).
- Routes: inject / list / delete, guarded to demo tenant + `REVERSA_CHAOS=1` —
  `reversa/apps/api/src/reversa_api/routes/chaos.py`.
- Injection fires at most one matching rule per action execution, ordered by rule
  id; a `target_action` mismatch returns WITHOUT consuming `times_remaining`;
  chaos fires on the forward path only, never inside `_compensate_one` —
  `reversa/apps/api/src/reversa_api/engine/saga.py` (`_consume_chaos`).
- 10-step onboarding template: 1 crm.validate_customer, 2 crm.create_organization,
  3 identity.create_workspace, 4 identity.provision_users, 5 support.create_queue,
  6 billing.create_profile (deps [2]), 7 identity.assign_manager,
  8 support.create_checklist, 9 core.consistency_check (deps [4,6,7,8]),
  10 notify.send_summary/IRREVERSIBLE (deps [9]) —
  `reversa/apps/api/src/reversa_api/templates/onboarding.py`.
- `notify.send_summary` is IRREVERSIBLE (compensate refuses);
  `billing.create_profile` is CONDITIONALLY_REVERSIBLE (refuses if
  `invoice_issued`) — `connectors/services.py`.

## A. Fault injection (CM-01–CM-07)

| ID | Scenario | Fault / target | Expected terminal state | Coverage |
|---|---|---|---|---|
| CM-01 | Billing 500s exhaust retries | `http500` ×5 on `demo-billing` | `COMPENSATED`; reverse order 8,7,5,4,3,2,1; seqs 9–10 `SKIPPED`; resources restored; chain valid | EXISTS — `reversa/apps/api/tests/test_chaos.py::test_billing_failure_compensates_everything` |
| CM-02 | Timeout reconciles then succeeds | `timeout` ×1 on `demo-crm/crm.validate_customer` | `COMPLETED`; `chaos.injected` + `UNKNOWN_OUTCOME` in events; 10× `VERIFIED` | EXISTS — `test_engine_units.py::test_unknown_outcome_reconciles_to_failed_then_retries` |
| CM-03 | Rate-limit retries with backoff | `http429` ×5 on `demo-billing` | `COMPENSATED`; `RETRY_SCHEDULED` + `action.retry_wait` events present | MISSING |
| CM-04 | Malformed response fails fast | `malformed` ×1 on `demo-billing` | `COMPENSATED`; `FAILED` with NO `RETRY_SCHEDULED` (non-retryable) | MISSING |
| CM-05 | Worker crash reconciles | `crash` ×1 on `demo-crm/crm.validate_customer` | `COMPLETED` via `UNKNOWN_OUTCOME` → reconcile (distinct `CHAOS_CRASH` code) | MISSING |
| CM-06 | Latency degrades, never fails | `latency` ×1 on `demo-billing` | `COMPLETED`; `chaos.injected` present; no `FAILED` states | MISSING |
| CM-07 | Early-step failure, minimal compensation | `http500` ×5 on `demo-crm/crm.create_organization` (seq 2) | `COMPENSATED`; seq 1 `COMPENSATED`, seqs 3–10 `SKIPPED` | MISSING |

## B. Rule API and guards (CM-08–CM-12)

| ID | Scenario | Request | Expected | Coverage |
|---|---|---|---|---|
| CM-08 | Real tenant forbidden | Inject as non-demo org | `403` | EXISTS — `test_security.py::test_chaos_forbidden_for_real_tenant` |
| CM-09 | Rule lifecycle | POST → GET lists → DELETE → GET empty; DELETE unknown | `201`/`200`/`200`; unknown → `404` | MISSING |
| CM-10 | Input validation | Unknown fault; unknown connector; `times` 0 / 11 | `422` in all cases | MISSING |
| CM-11 | Action scoping + times budget | Rule for action A while B runs (same connector); `times=1` then clean retry | Mismatch never fires and never consumes budget; single-shot fault → `COMPLETED` | MISSING |
| CM-12 | Flag + org isolation | `REVERSA_CHAOS=0` inject; org-A rule vs org-B workflow | `403`; org B `COMPLETED` unaffected | MISSING |

## C. Compensation outcomes (CM-13–CM-16)

| ID | Scenario | Setup | Expected terminal state | Coverage |
|---|---|---|---|---|
| CM-13 | Conditional compensation refused | `invoice_issued` set on billing profile mid-run + billing chaos | `PARTIALLY_COMPENSATED` | MISSING |
| CM-14 | External change blocks compensation (e2e) | Version-bump a `VERIFIED` resource mid-run, then fail billing | `PARTIALLY_COMPENSATED` (or `MANUAL_REQUIRED`); store-level raise EXISTS — `test_chaos.py::test_concurrent_modification_blocks_compensation`, e2e MISSING | MISSING (e2e) |
| CM-15 | Irreversible step forces human path | Custom plan: `notify.send_summary` (VERIFIED) then failing billing step | `MANUAL_REQUIRED` with manual item naming notify | MISSING |
| CM-16 | Late read-only failure | `http500` ×5 on `reversa-core/core.consistency_check` (seq 9) | `COMPENSATED`; seq 10 `SKIPPED` (never sent) | MISSING |

## D. Concurrency and crash recovery (CM-17–CM-18)

| ID | Scenario | Setup | Expected | Coverage |
|---|---|---|---|---|
| CM-17 | Crash mid-compensation recovers | Leave action in `COMPENSATING` at startup | `COMPENSATION_FAILED` → bounded retry (≤3) → `PARTIALLY_COMPENSATED`; startup path EXISTS in `reconcile_on_startup`, test MISSING | MISSING |
| CM-18 | Compensated replay is idempotent | Re-execute a `COMPENSATED` workflow | `replay: true`, state stays `COMPENSATED`, no duplicate effects (COMPLETED-replay EXISTS — `test_engine_units.py::test_double_execute_is_idempotent`) | MISSING |

## E. End-to-end and benchmarks (CM-19–CM-20)

| ID | Scenario | Harness | Expected | Coverage |
|---|---|---|---|---|
| CM-19 | One-click Chaos Lab journey | `reversa/tests/e2e/smoke_browser.py` (`chaos-scenario`) | Chaos run finishes; recovery lists `COMPENSATED`; evidence `VALID` | EXISTS |
| CM-20 | Chaos recovery benchmark | `reversa/tests/performance/bench.py` (`--chaos 5`) | 5/5 `COMPENSATED`, chains valid; published in `docs/benchmarks/results.md` | EXISTS |

## Tally

- Covered: 5/20 (CM-01, CM-02, CM-08, CM-19, CM-20) + 2 partial (CM-14 store-level, CM-18 COMPLETED-sibling).
- Missing: 15 (priority order: CM-04, CM-03, CM-05, CM-10, CM-09, CM-11, CM-13, CM-14, CM-15, CM-06, CM-07, CM-16, CM-12, CM-17, CM-18).

## Observations for implementers (not changes)

1. `routes/chaos.py` line 27: the `body.fault != "latency"` check is redundant —
   `latency` is already in `CHAOS_FAULTS`. Harmless; CM-10 pins behavior either way.
2. Chaos cannot fire inside compensation (`_consume_chaos` is forward-path only),
   so CM-13/CM-14 must arrange blocked compensations via direct store writes.
3. `latency` consumes budget and blocks the single worker with `time.sleep(2)`;
   CM-06 should assert on delay tolerance, not exact timing.
4. Demo Lab lists `reversa-core` as an injectable connector; it is a real registry
   member (`CoreConnector`), so CM-16 is injectable from the UI as well.
