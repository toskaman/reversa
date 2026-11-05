# GitHub test-repo connector (AGENT-05, REVERSA V2 cycle 1)

Feasibility + contract design for one REAL connector against a dedicated
GitHub test repository. Status: **skeleton implemented, offline contract
tests green, live run pending (no token in this environment)**.

## Feasibility

| Question | Answer |
|---|---|
| API surface | GitHub REST Issues API: `POST /repos/{repo}/issues` (create), `POST .../issues/{n}/labels` (add), `PATCH .../issues/{n}` (update title/body/state), `GET .../issues/{n}` (verify-by-read), `DELETE .../labels/{name}` (label-remove). All stable, no beta headers. |
| Auth | Fine-grained PAT or classic token with Issues RW on ONE test repo, via env (`REVERSA_GITHUB_TOKEN`, `GITHUB_TOKEN`, `GH_TOKEN`). Token never logged, stored, or echoed in errors. |
| Deletion | **Not possible.** The Issues API has no delete endpoint. Compensation closes (`state: closed`, `not_planned`); history stays visible. All copy says "close", never "delete/undo". |
| Idempotency | No server-side key. Client-side guard: `idempotency_key` is embedded as a `<!-- reversa:{key} -->` body marker and open issues (first page) are scanned before create. Best-effort; concurrent duplicates remain possible. |
| Rate limits | 5k req/h authenticated; our cycle uses ~6 calls. 429/5xx map to retryable `ConnectorError`; timeouts map to retryable + uncertain (engine reconciles via verify-by-read). |
| Token in this env | **Absent** (checked 2026-11-05: `GITHUB_TOKEN`, `GH_TOKEN`, `REVERSA_GITHUB_TOKEN`, `GITHUB_PAT`, `GH_PAT` all unset). Live test skips honestly. |

## Contract design

Connector id `github`, schema `v1`. Follows `connectors/sdk.py`
(`execute` / `verify` / `compensate`, typed errors, preconditions).

| Action | Inputs | Verify-by-read | Compensation | Approval |
|---|---|---|---|---|
| `github.create_issue` | repo, title, body?, labels?, idempotency_key? | GET issue: number + title match, state open | Close as `not_planned` (+ honest note) | APPROVAL_REQUIRED, CONDITIONALLY_REVERSIBLE |
| `github.add_labels` | repo, issue_number, labels | GET issue: added labels ⊆ current labels | Remove only labels this action added | AUTO_ALLOWED, FULLY_REVERSIBLE |
| `github.update_issue` | repo, issue_number, title?, body? | GET issue: title matches output | Restore captured previous title/body; refuse if uncaptured | AUTO_ALLOWED, FULLY_REVERSIBLE |
| `github.close_issue` | repo, issue_number, reason? | GET issue: state closed | Reopen | AUTO_ALLOWED, FULLY_REVERSIBLE |

Error codes: `GITHUB_NO_TOKEN` (non-retryable), `GITHUB_API_ERROR`
(non-retryable 4xx), `GITHUB_RETRYABLE` (429/5xx), `GITHUB_TIMEOUT`
(retryable + uncertain), `COMPENSATION_REFUSED` (missing ref / uncaptured
previous values).

## Files

- `reversa/apps/api/src/reversa_api/connectors/github.py` — skeleton
  (real httpx calls; `transport` seam for offline tests; explicit
  `register_github()`, NOT auto-registered).
- `reversa/apps/api/tests/test_github_contract.py` — 12 offline tests
  (contract shape, preconditions, token redaction, MockTransport
  execute/verify/compensate cycles, retryable mapping) + 1 live test
  that skips without token + `REVERSA_GITHUB_TEST_REPO`.

## To go live (follow-up)

1. Create a dedicated test repo (e.g. `reversa-e2e-probes`) and a token
   scoped to it; export `REVERSA_GITHUB_TOKEN` + `REVERSA_GITHUB_TEST_REPO`
   in the demo/CI env only — never commit them.
2. Run `pytest tests/test_github_contract.py -v`; expect 13 passed
   (live test un-skipped) and one closed probe issue in the test repo.
3. Decide registration: call `register_github()` in `register_all()` (or a
   feature flag) so the engine/planner can use it; add planner template
   coverage if the demo needs it.
4. Optional hardening: label allowlist, repo allowlist env guard, wider
   idempotency scan, ETag-based verify.
