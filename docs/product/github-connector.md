# GitHub test-repo connector (AGENT-05, REVERSA V2 cycle 2)

One REAL connector against a dedicated GitHub test repository.
Status: **allowlist + registration decision implemented, 32 offline
tests green + 1 live test skipping honestly (no token in this
environment)**.

## Feasibility

| Question | Answer |
|---|---|
| API surface | GitHub REST Issues API: `POST /repos/{repo}/issues` (create), `POST .../issues/{n}/labels` (add), `PATCH .../issues/{n}` (update title/body/state), `GET .../issues/{n}` (verify-by-read), `DELETE .../labels/{name}` (label-remove). All stable, no beta headers. |
| Auth | Fine-grained PAT or classic token with Issues RW on ONE test repo, via env (`REVERSA_GITHUB_TOKEN`, `GITHUB_TOKEN`, `GH_TOKEN`). Token never logged, stored, or echoed in errors. |
| Repo allowlist | `REVERSA_GITHUB_ALLOWED_REPOS` (comma-separated `owner/name`); a lone `REVERSA_GITHUB_TEST_REPO` counts as a single-entry allowlist. Deny-by-default: empty allowlist allows nothing; comparison is case-insensitive. Enforced in `execute` / `verify` (`False`) / `compensate` before any network use (`GITHUB_REPO_NOT_ALLOWED`, non-retryable). |
| Registration | `registration_decision()` registers ONLY when token + non-empty allowlist are both configured; otherwise the connector stays absent from the registry with an honest reason, and `register_github()` raises `GITHUB_NOT_CONFIGURED` instead of registering. The module never self-registers. |
| Deletion | **Not possible.** The Issues API has no delete endpoint. Compensation closes (`state: closed`, `not_planned`); history stays visible. All copy says "close", never "delete/undo". |
| Idempotency | No server-side key (`SUPPORTS_SERVER_IDEMPOTENCY = False`): no `Idempotency-Key` header is sent — the server would silently ignore it. Client-side guard for create only: `idempotency_key` is embedded as a `<!-- reversa:{key} -->` body marker and open issues (first page) are scanned before create; replays return `idempotent_replay: True`. Label-add, update and close are naturally idempotent (safe to retry unchanged). |
| Rate limits | 5k req/h authenticated; our cycle uses ~6 calls. 429/5xx map to retryable `ConnectorError`; timeouts map to retryable + uncertain (engine reconciles via verify-by-read). |
| Token in this env | **Absent** (checked 2026-11-05: `REVERSA_GITHUB_TOKEN`, `GITHUB_TOKEN`, `GH_TOKEN`, `GITHUB_PAT`, `GH_PAT`, `REVERSA_GITHUB_ALLOWED_REPOS`, `REVERSA_GITHUB_TEST_REPO` all unset). Live test skips honestly. |

## Contract design

Connector id `github`, schema `v1`. Follows `connectors/sdk.py`
(`execute` / `verify` / `compensate`, typed errors, preconditions).
Every action requires `repo` to be allowlisted (declared in each
contract's `input_schema` as `owner/name, must be allowlisted`).

| Action | Inputs | Verify-by-read | Compensation | Approval |
|---|---|---|---|---|
| `github.create_issue` | repo, title, body?, labels?, idempotency_key? | GET issue: number + title match, state open | Close as `not_planned` (+ honest note) | APPROVAL_REQUIRED, CONDITIONALLY_REVERSIBLE |
| `github.add_labels` | repo, issue_number, labels | GET issue: added labels ⊆ current labels | Remove only labels this action added | AUTO_ALLOWED, FULLY_REVERSIBLE |
| `github.update_issue` | repo, issue_number, title?, body? | GET issue: title matches output | Restore captured previous title/body; refuse if uncaptured | AUTO_ALLOWED, FULLY_REVERSIBLE |
| `github.close_issue` | repo, issue_number, reason? | GET issue: state closed | Reopen | AUTO_ALLOWED, FULLY_REVERSIBLE |

Error codes: `GITHUB_NO_TOKEN` (non-retryable),
`GITHUB_REPO_NOT_ALLOWED` (non-retryable, refused before network),
`GITHUB_NOT_CONFIGURED` (non-retryable, registration refused),
`GITHUB_API_ERROR` (non-retryable 4xx), `GITHUB_RETRYABLE` (429/5xx),
`GITHUB_TIMEOUT` (retryable + uncertain), `COMPENSATION_REFUSED`
(missing ref / uncaptured previous values).

## Files

- `reversa/apps/api/src/reversa_api/connectors/github.py` — real httpx
  calls; `transport` / `allowed_repos` seams for offline tests; explicit
  `register_github()` guarded by `registration_decision()`, NOT
  auto-registered.
- `reversa/apps/api/tests/test_github_contract.py` — 32 offline tests
  (contract shape, preconditions, token redaction, MockTransport
  execute/verify/compensate cycles, retryable mapping, allowlist
  enforcement on all actions, registration decision, idempotency
  honesty) + 1 live test that skips without token + allowlisted
  `REVERSA_GITHUB_TEST_REPO`.

## To go live (follow-up)

1. Create a dedicated test repo (e.g. `reversa-e2e-probes`) and a token
   scoped to it; export `REVERSA_GITHUB_TOKEN`,
   `REVERSA_GITHUB_ALLOWED_REPOS=<owner/repo>` (+ optionally
   `REVERSA_GITHUB_TEST_REPO` for the live test) in the demo/CI env
   only — never commit them.
2. Run `pytest tests/test_github_contract.py -v`; expect 33 passed
   (live test un-skipped) and one closed probe issue in the test repo.
   Without config expect 32 passed + 1 honestly skipped.
3. Decide registration: call `register_github()` where the app composes
   connectors (it refuses with `GITHUB_NOT_CONFIGURED` unless
   token+allowlist are set, so unconfigured envs simply have no
   `github` connector); add planner template coverage if the demo
   needs it.
4. Optional hardening: label allowlist, wider idempotency scan,
   ETag-based verify.
