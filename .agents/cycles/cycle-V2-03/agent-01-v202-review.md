# AGENT-01 — V2-02 Merged-Diff Design Review (REVERSA V2 cycle 3)

Date: 2026-11-05. Reviewer: AGENT-01 (Architect).
Target: committed merge `3fad9e4` ("V2-02: Recovery Proof manifest, resume,
guest sessions, rate limits, F2 fix, tickets UX, R1/D1/R3 (143 green)").
Scope: regressions, layering violations, dead code in the merged V2-02 diff
plus the R1/D1/R3 fixes; verdict on each fix with file:line.

Method note (racing tree, again): the working tree is dirty with concurrent
V2-03 work (`git status` shows modified `ratelimit.py`,
`test_guest_sessions.py`, `github-connector.md`, 4 web files, plus untracked
`test_connectors_routes.py` and `JuryLaunch.tsx`). All verdicts and line
numbers below are taken from the COMMITTED blob (`git show HEAD:<path>` /
`git grep HEAD`) or from files verified clean via `git status`/`git diff`.
`ratelimit.py` was re-read from the committed blob because the working copy
carries cycle-3 hardening. Tests were run both on the tree and on a pristine
`git archive` extract; see §Tests.

## Verdict

V2-02 as merged is sound: R1, D1 and R3 are REALLY fixed (code + tests, all
green), no regressions found in the reviewed surface, no new dead code, one
new minor layering wart (private-engine import, justified), and two minor
robustness nits in new code (404-sniffing fragility, CLI malformed-bundle
crash). Pre-existing items F3, R2, D5/D7, `?token=` fallback and the
`CANCELLED` redundancies carry over unchanged — noted, not regressed.

## R1 — GitHub verify conflates error with absence: FIXED (verified)

- `connectors/github.py:368-417` (committed): `verify()` now raises
  `ConnectorError` on EVERY error path — missing token (`_require_token`,
  380), missing/unreadable refs (`GITHUB_VERIFY_UNVERIFIABLE`, 384-395),
  allowlist refusal (`require_allowed_repo`, 388, before any network),
  transport/API failures (propagate from `_request`, 399-402), unknown
  action (`UNKNOWN_ACTION`, 415-417). `False` is returned only for a clean
  HTTP 404 (400-401) or a state mismatch on a successfully read issue
  (403-414). The saga tri-state (`engine/saga.py:68-107`) therefore reads
  all GitHub errors as INDETERMINATE. The latent HIGH is closed.
- Tests (committed, green): `test_verify_500_raises_not_false`,
  `test_verify_404_is_genuine_absence`, `test_verify_unknown_action_raises`
  (`tests/test_github_contract.py:238-273`), `test_verify_without_token_raises`
  (:119-124), `test_verify_disallowed_repo_raises_without_network` (:360-367).
- Nit (new, minor — issue 1): the 404 carve-out sniffs the exception string:
  `" 404 " in str(exc)` (`github.py:400`), where `str(exc)` is the formatted
  message `"GitHub API {status} on {method} {path}: {body[:300]}"`
  (`github.py:331-336`; `ConnectorError.__init__` passes message to
  `super().__init__`, `sdk.py`). A non-404 4xx whose body happens to contain
  `" 404 "` (e.g. 403 `...error 404...`) would misread as absence. Narrow
  but real; attach a structured `status_code` to `ConnectorError` and match
  on it. Known test gap (also noted in the in-flight cycle-3 doc edit): no
  test wires a raising GitHub `verify()` through `_verify_effect`
  end-to-end (both sides covered separately).

## D1 — Cancel-route allowlist bypass: FIXED (verified)

- `routes/workflows.py:236-273` (committed): cancel now (a) refuses
  COMPENSATING (240-242) and terminal (243-244); (b) refuses with 409 when
  any action is in-flight — CLAIMED/EXECUTING/SUCCEEDED/VERIFYING/
  UNKNOWN_OUTCOME/COMPENSATION_PENDING/COMPENSATING (250-257), closing the
  freeze-under-terminal gap for those states; (c) routes every hop through
  `_transition_act` with journaling, keeping the RETRY_SCHEDULED→PENDING
  drain hop (263-268); (d) rolls back the whole transaction on
  `InvalidTransition` (269-271), so the workflow-level CANCELLED set at
  line 258 is atomic with the action hops — no half-cancelled state.
- Tests (committed, green): `test_cancel_journals_retry_drain_hops` and
  `test_cancel_refused_with_inflight_action`
  (`tests/test_security.py:238-303`); pre-existing `test_cancel_ready_workflow`
  still passes.
- Residual hygiene (minor, disclosed direction): cancel from MANUAL_REQUIRED
  (or with FAILED/VERIFIED leftovers) leaves VERIFIED/FAILED actions
  non-terminal under a terminal CANCELLED workflow; the pump refuses terminal
  workflows so they freeze, fail-safe. Workflow VERIFYING→CANCELLED still
  409s (no edge in `states.py:64`) — pre-existing, now also guarded by (b).

## R3 — SSE fallback Bearer [REDACTED] sensitivity: FIXED (verified)

- `routes/workflows.py:373-378` (committed): the `?token=` SSE fallback now
  parses the scheme case-insensitively (`scheme.lower() == "be"+"arer"`),
  matching `get_current_org` (`auth.py:87-94`). `removeprefix` is gone from
  this path (only remaining `removeprefix` is the unrelated event-ref
  parser in `recovery.py:660`).
- Test (committed, green): `test_stream_bearer_scheme_case_insensitive`
  (`tests/test_security.py:221-235`).

## Regressions: none found

- No direct state assignments survive outside the allowlisted helpers: the
  only `wf.state =` / `action.state =` writes are inside `_set_state`
  (`workflows.py:71`) and `_transition_wf`/`_transition_act`
  (`saga.py:113,125`), all guarded by `check_*_transition`. Committed-wide
  sweep confirms.
- Cancel hardening does not break the happy path (suite green, incl. the
  pre-existing cancel test); resume route reuses `_get_owned` (cross-tenant
  404 preserved); guest/ratelimit middlewares are strict passthrough for
  non-guests/unwatched paths; middleware order in `main.py:52-54` matches
  its comment (Guest outer, RateLimit inner).
- RPE is read-only as claimed (SELECTs + `DemoStore` reads only,
  `recovery.py:693-755`); `DemoStore.get` PK-only reads cannot cross orgs
  (autoincrement PKs never reassigned — redteam's conclusion re-confirmed).
- `?token=` fallback still live (`workflows.py:366-378`) but the committed
  web client uses `?ticket=` exclusively (`EventTimeline.tsx` committed) —
  removal-ready (F6), not a regression.
- Pre-existing behaviors explicitly NOT regressed: F3 chaos single-rule
  shadowing (`saga.py:181-194`, verbatim), R2 hot-path verify-error→
  VERIFY_FAILED (`saga.py:268-272`, verbatim), `?token=` ticket-pop-before-
  bind (R4), in-memory stores ×3 (all disclosed in-code), D2/D3/D4/D6
  untouched.

## Layering

- L1 [NEW, minor, justified]: `routes/workflows.py:20-25` imports the
  private `_transition_act` from `engine.saga` for the D1 fix. A route
  reaching into a `_`-private engine helper is a wart; but it is exactly
  what closes the journaling bypass, and the alternative (duplicating the
  transition+append logic in the route) would be worse. Recommend promoting
  to a public `transition_action` (or a `cancel_actions` engine helper) and
  de-underscoring — no behavior change.
- L2 [NEW, minor, acceptable]: `routes/recovery.py:27` imports `DemoStore`
  and `SERVICE_STORES` from `connectors.services` — a route depending on a
  connector module. Acceptable: the RPE is explicitly a read-only observer
  over demo state, uses only read methods, and the dependency direction
  (routes→connectors) matches the rest of the codebase. No cycle.
- L3 [CARRYOVER]: `connectors/services.py` hosts `demo_router` (HTTP) and
  imports `..auth` — connector layer depending on route/auth layer.
  Pre-existing (V2-01), untouched by V2-02. No import cycle (`auth` does not
  import connectors). Leave.
- L4 [CARRYOVER]: guest-quota/chaos-deny/rate-limit enforcement by
  path-string matching in middleware (`auth.py:342-368`,
  `ratelimit.py:41-51`) is fail-open for future endpoints (QA R3). V2-02
  endpoints are all covered by tests; note for cycle-3 route additions.

## Dead code

- No new dead code introduced by V2-02. One V2-01 dead item REMOVED:
  `VultrInferenceProvider._input_keys` is gone (`planner/vultr.py` rewritten
  at 200 lines with real metering) — good.
- Carried over unchanged (not regressions): unreachable `elif`
  `recovery.py:618-620` (second `all_restored and not comp_started` branch;
  cosmetic, keep-or-drop); `wf.state == "CANCELLED"` redundancies
  (`workflows.py:218,243,403`, `saga.py:708,855` — CANCELLED ∈ WF_TERMINAL);
  `invoice_issued` still 1 read / 0 writers src+tests-wide
  (`services.py:528`, committed-wide `git grep`); `MANUAL_ONLY` still never
  assigned by any connector (only `IRREVERSIBLE` at `services.py:549`).
- The GitHub connector is NOT dead code: still explicitly registered only
  (`register_github`, `github.py:548-561`), now with the R1 gate satisfied.

## Files read / modified

- Read (committed content; working-tree reads only for files verified clean
  via git status/diff, committed blobs via `git show`/`git grep` otherwise):
  `connectors/github.py` (full), `routes/workflows.py` (full), `auth.py`
  (full), `engine/saga.py` (full), `engine/states.py` (full),
  `routes/recovery.py` (full, 755 lines), `ratelimit.py` (full, committed
  blob), `routes/guest_sessions.py` (full), `routes/health.py` (full),
  `main.py` (full), `evidence.py` (full), `db.py` (full), `cli.py` (full),
  `planner/vultr.py` (full), `connectors/services.py` (DemoStore + core +
  router blocks), `connectors/sdk.py` (ConnectorError), `connectors/__init__.py`,
  `tests/test_security.py` (cancel + SSE blocks),
  `tests/test_github_contract.py` (verify block), prior-cycle
  `agent-01-v201-review.md`, `agent-14-qa-v202.md`, `agent-20-redteam.md`
  (full), `release-gates.md` (full).
- Modified: `.agents/cycles/cycle-V2-03/agent-01-v202-review.md` (this file) ONLY.

## Commands run

- `git status` / `git log --oneline -15` — HEAD `3fad9e4`, tree dirty with
  V2-03 in-flight work (racing-tree discipline applied throughout).
- `git show --stat HEAD` / `git diff HEAD~1 HEAD --name-only` — 74 files,
  +10062/-193.
- `git diff HEAD -- ratelimit.py github-connector.md test_guest_sessions.py`
  — identified cycle-3 in-flight changes; excluded from verdicts.
- Full suite on tree: `reversa/apps/api/.venv/.../python -m pytest
  reversa/apps/api/tests -q -p no:cacheprovider` →
  **143 passed, 2 skipped** in 40.06 s.
- Pristine committed suite: `git archive -o $env:TEMP/v202.tar HEAD <api
  src+tests>` + extract + `PYTHONPATH=<extracted src> .../.venv/python -m
  pytest <extracted tests> -q -p no:cacheprovider` →
  **143 passed, 2 skipped** in 90.71 s. Matches the merge commit's
  "143 green" exactly. (Both skips pre-existing/honest; the one warning is
  the standing Starlette/httpx deprecation.)
- Sweeps (committed): `.state =` assignments, `MANUAL_ONLY`/`invoice_issued`/
  `_input_keys`, `compensation_capability=` assignments, `rev_jury` in
  `git ls-files` (absent) and working tree (absent), `?token=`/`?ticket=` in
  committed `EventTimeline.tsx`, RPE-spec header + chaos-matrix tally +
  pilot-offer wording, verification-matrix staleness.

## Tests

- Committed V2-02 suite: 143 passed, 2 skipped (quoted verbatim above, both
  runs). Delta vs the 137/2 seen by QA/redteam mid-cycle = +6 R1/D1/R3
  tests (3 github verify + 2 cancel + 1 SSE case), all read in full.
- Coverage of the reviewed surface is real: R1 error-vs-absence matrix
  (500/404/unknown-action/no-token/disallowed-repo), D1 journaled-drain +
  in-flight-refusal incl. post-refusal state pins (wf still READY, action
  still EXECUTING), R3 lowercase-scheme stream auth.
- Gaps (unchanged/adjacent, none blocking): no GitHub-raise→INDETERMINATE
  integration test through `_verify_effect` (issue 1); no MANUAL_REQUIRED
  e2e; no `/connectors*` tests on the committed tree (a cycle-3 sibling is
  adding `test_connectors_routes.py` in the working tree — out of scope).

## Issues (actionable)

1. R1-nit: `github.py:400` — replace `" 404 " in str(exc)` with a structured
   `status_code` on `ConnectorError` (set in `_request`), matched exactly.
   Add the GitHub-raise→`_verify_effect`→INDETERMINATE integration test.
2. L1: promote saga `_transition_act` to a public engine helper (or add
   `cancel_actions`) and use it from the cancel route; behavior unchanged.
3. Minor/new: `cli.py:73` — `verify_bundle` indexes
   `bundle["workflow"]["id"]` unguarded; a malformed export crashes with a
   traceback instead of a clean INVALID. Wrap in a usage/INVALID verdict.
4. Cosmetic (batch with next docs pass): drop the unreachable
   `recovery.py:618-620` branch or annotate it; fix chaos-matrix rows still
   marked MISSING for CM-03/04/05/09/10 (tally already says 10/20 —
   N3 half-fixed); verification-matrix still says 19/19 (N6, now badly
   stale vs 143); pilot-offer still repeats the U7 mass-sends wording (N1);
   N5 orphan confirmed gone from tree and never committed — closed.

## Risks

- Racing-tree hazard persists into cycle 3: V2-03 files landed DURING this
  review (my first full-suite run predates 17 in-flight tests). Future
  reviewers must keep the committed-vs-dirty discipline.
- The 404-sniff (issue 1) is the only place where the R1 fix itself could
  still mistake an error for absence — narrow (requires " 404 " inside a
  non-404 error body) but exactly the class P0-REC-01 forbids; fix before
  any demo that reconciles against a live GitHub repo.
- `register_github()` is now SAFE from R1's original form (gate satisfied),
  but the missing end-to-end test means the reconcile path against real
  GitHub is still unproven — keep it out of the jury live path until issue
  1's test exists.
- Committed `ratelimit.py` has an unbounded `_WINDOWS` keyed by
  caller-supplied credentials (memory DoS) — a cycle-3 sibling is already
  hardening it in the working tree; review that diff on its own merits,
  don't conflate with this verdict.

## Confidence

- HIGH on R1/D1/R3 fixed (exact committed lines + the 6 tests read in full
  + both suites executed and quoted verbatim), on 143/2 (pristine extract
  matches the merge message), on dead-code carryovers (committed-wide
  greps), on N5-closed/N2-fixed/N3-tally/N1-open/N6-open (committed file
  reads), on no-new-dead-code and the layering items (full-file reads of
  every touched source module).
- MEDIUM on "no other regressions": full reads of all 16 touched/added API
  sources, but no live API reproduction (mandate is review; redteam already
  live-proved the adjacent behaviors, and R1/D1/R3 change only the paths
  their tests pin).
- LOW on prod behavior (never touched — localhost-only by mandate; in fact
  no server was started at all this review).

## Next task

- Owner of GitHub wiring: issue 1 (structured 404 + e2e INDETERMINATE test),
  then the pre-existing repo-allowlist/credential-scoping gate (offsec F-05)
  before any live reconcile demo.
- Whoever owns routes: issue 2 (de-underscore `_transition_act`) + F6
  `?token=` removal now that no committed web caller uses it.
- Docs owner: single pass for N1 wording + N6 matrix rewrite + matrix-row
  MISSING cells + stale README "19 passed" (unchanged since V1).
- V2-03 QA: re-run the quoted suites post-merge; the 143/2 baseline here is
  the number to beat.
