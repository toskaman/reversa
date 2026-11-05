# GitHub test-repo connector (AGENT-05, REVERSA V2 cycle 3)

One REAL connector against a dedicated GitHub test repository.
Status: **allowlist + registration decision + R1 verify fix implemented,
35 offline tests green + 1 live test skipping honestly (no token in this
environment)**. Verified 2026-11-05 on the committed tree (`35 passed, 1 skipped`; skip reason: "no GitHub token/test repo in env (or repo not allowlisted); live contract test skipped honestly").

## Feasibility

| Question | Answer |
|---|---|
| API surface | GitHub REST Issues API: `POST /repos/{repo}/issues` (create), `POST .../issues/{n}/labels` (add), `PATCH .../issues/{n}` (update title/body/state), `GET .../issues/{n}` (verify-by-read), `DELETE .../labels/{name}` (label-remove). All stable, no beta headers. |
| Auth | Fine-grained PAT or classic token with Issues RW on ONE test repo, via env (`REVERSA_GITHUB_TOKEN`, `GITHUB_TOKEN`, `GH_TOKEN`). Token never logged, stored, or echoed in errors. |
| Repo allowlist | `REVERSA_GITHUB_ALLOWED_REPOS` (comma-separated `owner/name`); a lone `REVERSA_GITHUB_TEST_REPO` counts as a single-entry allowlist. Deny-by-default: empty allowlist allows nothing; comparison is case-insensitive. Enforced in `execute` / `verify` (raises) / `compensate` before any network use (`GITHUB_REPO_NOT_ALLOWED`, non-retryable). |
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
(missing ref / uncaptured previous values), `GITHUB_VERIFY_UNVERIFIABLE`
(non-retryable, verify called without readable refs),
`GITHUB_TRANSPORT` (retryable, non-timeout transport failure),
`UNKNOWN_ACTION` (non-retryable, verify/compensate cannot interpret
the action).

## R1 fix — verify() never mistakes an error for absence (cycle 3, verified)

Finding (V2-02 review R1, confirmed by redteam): `verify()` used to
return `False` on verifier errors (missing token, transport failure,
unreadable refs, unknown action). But the saga tri-state
(`_verify_effect`, `engine/saga.py:68-107`) maps a clean `False` to
`ABSENT_CONFIRMED` ("effect confirmed absent" -> FAILED + idempotent
retry) and only a raised `ConnectorError`/crash/non-boolean to
`INDETERMINATE` (defer: stays UNKNOWN/VERIFYING/COMPENSATING). So a
GitHub outage or lost token during reconcile/resume would have been
read as absence proof — exactly what P0-REC-01 forbids ("a verifier
error is never absence proof").

Fix (committed, in `connectors/github.py:368-417`): `verify()` now
raises `ConnectorError` on EVERY error path — missing token
(`GITHUB_NO_TOKEN`), missing/unreadable refs
(`GITHUB_VERIFY_UNVERIFIABLE`), allowlist refusal
(`GITHUB_REPO_NOT_ALLOWED`, before any network use), transport/API
failures (`GITHUB_TIMEOUT`/`GITHUB_TRANSPORT`/`GITHUB_RETRYABLE`/
`GITHUB_API_ERROR` propagate), unknown action (`UNKNOWN_ACTION`) —
so the saga reads them all as INDETERMINATE. `False` is returned ONLY
when a clean read proves the expected state is absent: a clean HTTP
404 on the issue read (genuinely proves the issue does not exist), or
a state mismatch on a successfully read issue (wrong number/title/
state/labels).

Proof (all green 2026-11-05, `35 passed, 1 skipped`):
`test_verify_500_raises_not_false` (500 -> raises, i.e.
INDETERMINATE, not `False`), `test_verify_404_is_genuine_absence`
(404 -> `False`, the one true absence proof),
`test_verify_unknown_action_raises`,
`test_verify_without_token_raises`,
`test_verify_disallowed_repo_raises_without_network`, and the
unreadable-refs raise inside `test_error_messages_never_contain_token`.

Known gap (bounded): no test wires a raising GitHub `verify()`
through `_verify_effect` end-to-end (transport error ->
INDETERMINATE -> stays VERIFYING). Both sides are covered
separately — GitHub raises (tests above), the engine defers on
INDETERMINATE (`test_engine_units.py`: corrupt-JSON and
resume-unknown cases) — but the wire between them is untested. Add
that integration test before relying on GitHub reconcile/resume in a
demo that kills the network mid-run.

## Files

- `reversa/apps/api/src/reversa_api/connectors/github.py` — real httpx
  calls; `transport` / `allowed_repos` seams for offline tests; explicit
  `register_github()` guarded by `registration_decision()`, NOT
  auto-registered.
- `reversa/apps/api/tests/test_github_contract.py` — 35 offline tests
  (contract shape, preconditions, token redaction, MockTransport
  execute/verify/compensate cycles, retryable mapping, allowlist
  enforcement on all actions incl. verify/compensate, registration decision,
  idempotency honesty, R1 verify tri-state: 500/unknown-action/no-token/
  disallowed-repo/unreadable-refs raise, only clean 404 reads as absent)
  + 1 live test that skips without token + allowlisted
  `REVERSA_GITHUB_TEST_REPO`.

## Live-enablement runbook

Goal: take the connector from "offline-verified" to "one live run
against the dedicated test repo", with rollback. Docs only here —
**no live calls were made** while writing this (no token in this
environment; the live test skips honestly). The human operator runs
the steps below.

### 0. Preconditions (do not skip)

- Committed tree contains the R1 fix (`verify()` raises on errors,
  `connectors/github.py:368-417`) and the allowlist + registration
  decision. Confirm with `git log --oneline -3` (expect the V2-02
  merge or later) and by reading `verify()` — `False` must appear
  only on the 404 path and the state-comparison returns.
- Offline suite green: `35 passed, 1 skipped` on
  `tests/test_github_contract.py` (see Files).

### 1. Token + allowlist + test repo (operator, ~10 min)

1. Create a DEDICATED test repo (e.g. `<org>/reversa-e2e-probes`).
   It will accumulate closed probe issues forever (issues cannot be
   deleted via the API) — never use a real project repo.
2. Mint a token scoped to THAT repo only: fine-grained PAT with
   Issues read/write on the single test repo, no other permissions.
   Classic PAT fallback: `repo` scope is broader — prefer
   fine-grained.
3. Export in the demo/CI env ONLY (shell session, CI secret store,
   or process env — never in a file that gets committed):
   - `REVERSA_GITHUB_TOKEN=<token>`
   - `REVERSA_GITHUB_ALLOWED_REPOS=<owner/repo>` (exactly the test
     repo; comma-separated if several)
   - `REVERSA_GITHUB_TEST_REPO=<owner/repo>` (same value; enables
     the live contract test)
4. Secret hygiene: the connector never logs the token (only env var
   NAMES appear in errors — covered by
   `test_error_messages_never_contain_token`). Still: never paste
   the token into chat logs, screenshots, jury recordings, or issue
   bodies; rotate immediately if exposed.

### 2. Registration (code change, one call site)

1. The module never self-registers. Call `register_github()` ONCE
   where the app composes connectors (API startup path). It enforces
   the token+allowlist decision itself: unconfigured envs raise
   `GITHUB_NOT_CONFIGURED` (catch-and-log at startup so the app
   boots WITHOUT the `github` connector) instead of registering a
   half-configured connector.
2. Verify registration state without secrets: call
   `registration_decision()` — `register: True` plus
   `allowed_repos: [<owner/repo>]` means ready; `register: False`
   plus `reason` names exactly what is missing (never credential
   values).
3. Planner coverage (only if the demo needs it): add a template that
   emits `github.*` actions against the allowlisted repo; keep
   `create_issue` APPROVAL_REQUIRED.

### 3. First live run (operator, ~5 min)

1. Dry check (no network): with the env set, run the offline suite
   again — still `35 passed`, and the live test should now be
   collected (not skipped).
2. Live contract test (makes REAL issues, then closes them):
   `pytest tests/test_github_contract.py -v -k live`. Expect
   `test_live_create_label_update_close_cycle` PASSED. It creates
   one `[reversa-test] contract probe ...` issue, labels it
   `reversa-test`, renames it, closes it as `completed`, and the
   `finally` block closes it even on mid-test failure.
3. Inspect the test repo in a browser: exactly one new issue,
   state closed, carrying the `reversa-test` label and the
   `(updated)` title. That is the visible proof of the live run.
4. Full suite: `pytest tests/test_github_contract.py -v` — expect
   36 passed (live test un-skipped). Without config the expectation
   stays `35 passed, 1 skipped`.
5. Rate-limit sanity: the live test uses ~6 API calls against a 5k/h
   budget — negligible. Do NOT loop it.

### 4. Rollback (any step fails, or token suspected leaked)

- **Immediate containment (seconds):** unset `REVERSA_GITHUB_TOKEN`
  (or remove it from the CI secret store) and restart the API
  process. The connector refuses everything without a token
  (`GITHUB_NO_TOKEN`) and `register_github()` raises
  `GITHUB_NOT_CONFIGURED`, so the app boots connector-less. No code
  revert needed for containment.
- **Token rotation:** revoke the token at github.com (Settings ->
  Developer settings -> tokens), mint a fresh repo-scoped token,
  update the env/secret store, restart. Old token is dead instantly.
- **Repo quarantine:** if the test repo is polluted or the wrong
  repo was allowlisted, shrink `REVERSA_GITHUB_ALLOWED_REPOS` back
  to the single correct repo (or empty = deny-all) and restart;
  refusals happen before any network use.
- **Code rollback:** the connector is additive and never
  self-registers — removing/never-merging the single
  `register_github()` call site fully unwires it. Probe issues left
  behind cannot be deleted (API limit); close them manually — they
  are harmless in the dedicated test repo.
- **Verify the rollback:** with the token unset, the suite must show
  `35 passed, 1 skipped` with the honest skip reason, and
  `registration_decision()` must report `register: False`.

### 5. Optional hardening (later)

Label allowlist, wider idempotency scan (beyond first page),
ETag-based verify, and the R1 integration test noted in the gap
above.
