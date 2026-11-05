# AGENT-01 — V2-01 Merged-Diff Design Review (REVERSA V2 cycle 2)

Date: 2026-11-05. Reviewer: AGENT-01 (Architect).
Target: committed merge `63bb949` ("V2-01: P0 SEC/REC fixes, SSE tickets, XSS escape,
GitHub skeleton, audits"). Scope: saga tri-state, SSE tickets, auth hardening,
GitHub skeleton; design regressions, dead code, contract breaks; D1 cancel-route
allowlist verdict with file:line.

Method note ( Racing tree): the working tree is dirty with concurrent V2-02 work
(`git status` shows ~19 modified + new files, e.g. `github.py` is 489 lines on disk
vs 400 committed, and changed between two reads seconds apart). All verdicts and
line numbers below are therefore taken from the COMMITTED blob (`git show 63bb949:<path>`
/ `git grep 63bb949`), not the working tree. Tests were run both ways; see §Tests.

## Verdict

V2-01 is sound: the security fixes are real and correctly sequenced, the tri-state
recovery design is coherent, and the GitHub skeleton is honestly staged. One
HIGH-severity design interaction to fix before the GitHub connector wires up
(R1: `verify()` conflates error with absence, defeating the tri-state guarantee),
one CONFIRMED carry-over (D1: cancel still bypasses the action allowlist), no
unintended contract breaks, no new dead code. Details below.

## D1 — Cancel-route allowlist bypass: CONFIRMED (still present, unchanged)

- `reversa/apps/api/src/reversa_api/routes/workflows.py:215-216` (committed):
  `action.state = "PENDING"` / `action.state = "SKIPPED"` by direct assignment,
  bypassing `check_action_transition` (`engine/states.py:107-109`) and the saga's
  `_transition_act` journaling (`engine/saga.py:121-132`). The intermediate
  RETRY_SCHEDULED -> PENDING hop is unjournaled; a single `action.state`
  from=prev to=SKIPPED event is emitted (`workflows.py:217-220`).
- Severity is bounded: both hops taken are individually legal
  (`PENDING -> SKIPPED` in `states.py:77`, `RETRY_SCHEDULED -> PENDING` in
  `states.py:84`), so this is an invariant/process bypass, not an illegal-state
  bug. The V2-01 diff does not touch the cancel handler (only its imports).
- Adjacent gap (same handler, worth a ticket): cancel only SKIPs
  PENDING/RETRY_SCHEDULED (`workflows.py:209-212`) while the workflow goes terminal
  CANCELLED. In-flight actions (CLAIMED/EXECUTING/SUCCEEDED/VERIFYING/VERIFIED) are
  left non-terminal under a terminal workflow; `_pump` (`saga.py:702`) refuses
  terminal workflows, so they freeze forever. No data corruption (effects already
  applied stay applied and journaled), but state-space hygiene suffers.
- Workflow-level cancel is correctly allowlisted: `_set_state`
  (`workflows.py:56-60`) enforces `check_workflow_transition`, so e.g.
  VERIFYING -> CANCELLED is refused (`states.py:64` has no CANCELLED edge) and
  surfaces as 409. Message text leaks internal transition language
  ("invalid workflow transition VERIFYING -> CANCELLED") — cosmetic only.

## Design regressions / interactions (ranked)

- R1 [HIGH, latent — zero prod impact while GitHub is unwired]:
  `GithubConnector.verify()` returns `False` on verifier errors:
  token/transport failure -> `False` (`connectors/github.py:240-243`),
  `ConnectorError` during re-read -> `False` (`github.py:252-253`), missing
  repo/number -> `False` (`github.py:247-248`), unknown action -> `False`
  (`github.py:266`). But `_verify_effect` (`engine/saga.py:101-104`) maps a clean
  `False` to `ABSENT_CONFIRMED` (absence proof) — only raised `ConnectorError` /
  crashes / non-boolean map to INDETERMINATE (`saga.py:95-100,105-107`). So a
  GitHub outage or lost token during reconcile/resume would be read as "effect
  confirmed absent" -> FAILED + idempotent retry, exactly what P0-REC-01 forbids
  ("a verifier error is never absence proof", `saga.py:76`). Fix before wiring:
  let `ConnectorError` propagate from `verify()` (or return a non-boolean) so the
  tri-state maps it to INDETERMINATE. The demo connectors do not share this flaw
  (they raise or answer cleanly).
- R2 [LOW]: the hot path `_run_claimed` (`saga.py:268-272`) still maps a verify
  `ConnectorError` to `ok=False` -> VERIFY_FAILED -> FAILED + retry. Pre-existing
  semantics, now philosophically inconsistent with the tri-state resume paths.
  Bounded: retries are idempotent-guarded; worst case burns attempts and can push
  an exhausted action into compensation. Consider routing the hot path through
  `_verify_effect` with INDETERMINATE -> stay VERIFYING.
- R3 [LOW, carry-over of redteam F6]: SSE `?token=` fallback still parses the
  header case-sensitively (`routes/workflows.py:323`
  `header.removeprefix("Bearer ")`) while `get_current_org` is case-insensitive
  (`auth.py:74`). `bearer <tok>` works everywhere except the SSE fallback.
  One-line fix when convenient.
- R4 [INFO]: `_redeem_stream_ticket` pops the ticket (`workflows.py:285`) before
  the wf-binding check (`workflows.py:288`), so a ticket presented to the wrong
  `wf_id` is destroyed and the client must re-mint. Fail-safe; minor UX only.
- R5 [INFO, documented]: ticket store is in-memory single-process
  (`workflows.py:268-272`); multi-worker needs DB/Redis before the `?token=`
  fallback is removed. Correctly disclosed in-code; no action for V2.
- R6 [OK]: fail-closed compensation for SUCCEEDED/VERIFYING (`saga.py:462-486`)
  assumes PRESENT unless ABSENT_CONFIRMED — sound. The VERIFYING -> VERIFIED hop
  on merely-unprovable effects is accurately journaled in the note; the event
  log preserves the distinction. No change needed.
- R7 [OK]: compensation gated on indeterminate unknowns (`saga.py:595-603`) is
  the right call (never orphan an unverified effect). A permanently-indeterminate
  verifier parks the workflow non-terminal; behavior is covered by test
  (`tests/test_chaos.py` indeterminate case) and matches the disclosed
  single-worker demo posture.
- R8 [COSMETIC, carry-over of offsec note]: `compare_digest` after a DB equality
  lookup (`auth.py:55-58`) adds no timing protection. Harmless; the strict Bearer
  parse + 512-char cap are the real wins. Leave or simplify with a comment.
- Pre-existing items explicitly NOT regressed by V2-01: chaos single-rule match
  (`saga.py:181-194`, redteam F3) untouched; double-execute race
  (`workflows.py:181-191`, F4) untouched; `/readyz` 200-when-degraded (F5)
  untouched; D2 evidence-seq race, D3 blocking sleeps, D4 claim journal, D6 no
  migrations — all untouched. V2-01 neither fixed nor worsened them.

## Contract breaks

- C1 [INTENDED, security fix for offsec F-01 CRITICAL]:
  `GET /demo/{service}/resources` dropped the `org_id` query param; org now comes
  from auth context (`connectors/services.py:578-591`). Legacy `?org_id=` is
  silently ignored (FastAPI drops unknown query params), covered by
  `test_demo_resources_client_org_id_ignored`. Verified no web callers pass
  `org_id` (committed-tree search: zero hits in `apps/web/{app,lib,components}`).
  Breaking only for external scripts hitting the anonymous endpoint — that was
  the vulnerability. Correct.
- C2 [ADDITIVE, correctly sequenced]: new `POST /workflows/{id}/stream-ticket`
  (201) and `?ticket=` on the SSE stream (`routes/workflows.py:301-311,314-324`).
  The committed web client still uses `?token=`
  (`apps/web/components/EventTimeline.tsx:32` committed), so retaining the
  fallback in V2-01 was REQUIRED, not dead weight. (Ticket migration visible in
  the working tree is V2-02 in-flight work, out of scope here.)
- C3 [OK]: `reconcile_on_startup` stats dict grew additively
  (`+verified/compensated/deferred/reconcile_pending/live`, `saga.py:753-755`).
  Sole consumer is a `print` in `main.py:33`. Backward compatible.
- C4 [MINOR, note for API consumers]: malformed auth scheme (`Token x`, bare
  garbage) now yields 401 via the empty-credential path (`auth.py:73-75`) instead
  of 403 from token-lookup miss. Legitimate `Bearer` clients unaffected; volume
  of 401-vs-403 in dashboards may shift slightly.

## Dead code

- No new dead code introduced by V2-01. Carried over unchanged (not regressions):
  `VultrInferenceProvider._input_keys` still returns `[]` with no callers
  (`planner/vultr.py:78-79` committed, D9/N1); `invoice_issued` still read once
  (`services.py:461` committed) with zero writers committed-tree-wide (D5);
  `MANUAL_ONLY` still declared but never assigned by any connector (D7 —
  `git grep 63bb949` shows only `saga.py:35`, `states.py:50`, `workflows.py:238`
  references); `wf.state == "CANCELLED"` redundancies (`workflows.py:206,349`,
  `saga.py:702`) where `CANCELLED` is already in `WF_TERMINAL` (`saga.py:37-44`).
- The GitHub skeleton is NOT dead code: unregistered by design (only explicit
  `register_github()`, `github.py:396-400`), covered by 13 contract tests, with
  honest limitation docs. Correct staging.

## Files read / modified

- Read (committed V2-01 blobs unless noted): `routes/workflows.py` (full),
  `engine/saga.py` (full), `engine/states.py` (full), `auth.py` (full),
  `routes/evidence.py` (full), `connectors/github.py` (full),
  `connectors/services.py:577-604` + `git grep` for `invoice_issued`/`MANUAL_ONLY`,
  `connectors/__init__.py`, `planner/vultr.py`, `main.py:32-33`,
  `apps/web/components/EventTimeline.tsx` (committed + working),
  `tests/test_security.py` + `test_engine_units.py` + `test_github_contract.py`
  + `test_planner_evidence.py` (names/assertions), prior-cycle
  `agent-01-arch-audit.md` (D1 source), `agent-11-offsec.md` (F-01..F-09),
  `agent-20-redteam.md` (F1..F7, U1..U26).
- Modified: `.agents/cycles/cycle-V2-02/agent-01-v201-review.md` (this file) ONLY.

## Commands run

- `git show --stat 63bb949` / `git show 63bb949 -- <5 core files>` — V2-01 diff.
- `git show 63bb949:<path>` + `git grep -n <term> 63bb949` — committed line numbers
  for every citation above (working tree is dirty with V2-02 work).
- `git archive -o $env:TEMP/v201.tar 63bb949 <api src+tests>` + extract to
  `%TEMP%/reversa-v201` — pristine committed tree for testing (no stash, no
  disturbance of siblings' uncommitted work).
- Committed V2-01 suite: `PYTHONPATH=<extracted src> .../.venv/python -m pytest
  <extracted tests> -q -p no:cacheprovider` → **49 passed, 2 skipped** in 32.6 s
  (matches the merge commit's "49 tests green").
- Dirty working-tree suite (V2-02 in-flight, for context only):
  `reversa/apps/api/.venv/.../python -m pytest reversa/apps/api/tests/ -q` →
  **65 passed, 2 skipped** in 37.4 s. The +16 delta is V2-02 siblings' new tests,
  not V2-01.

## Tests

- V2-01 committed: 49 passed, 2 skipped (see above). The 2 skips are the honest
  Vultr-not-configured conditional skips.
- Coverage of the reviewed surface is real: 17 security tests incl. stream-ticket
  single-use/binding/expiry and `org_id`-ignored isolation; tri-state unit tests
  (`test_unknown_outcome_reconciles_*`, `test_unreadable_state_defers_*`,
  `test_restart_resume_recovers_all_inflight_states`); HTML-escape regression
  (`test_html_export_escapes_untrusted_content`); 13 GitHub contract tests
  (offline MockTransport + 1 live, skipped without token).
- Gaps (unchanged from redteam notes, none introduced by V2-01): no end-to-end
  MANUAL_REQUIRED test, no literal-`timeout`-fault test, no process-boot test,
  no multi-worker SSE test (single-process is disclosed).

## Issues (actionable)

1. R1: `github.py:237-266` — make `verify()` propagate `ConnectorError` instead
   of returning `False` before the connector is registered. Add a tri-state test:
   transport-error verify -> INDETERMINATE (stays UNKNOWN/VERIFYING), not FAILED.
2. D1: `workflows.py:209-220` — route cancel through `_transition_act`
   (add explicit `RETRY_SCHEDULED -> SKIPPED` edge or journaled two-hop), and
   decide the policy for in-flight actions under cancel (leave-and-disclose vs
   interrupt). At minimum document that cancel freezes non-PENDING actions.
3. R3: `workflows.py:323` — reuse the strict case-insensitive Bearer [REDACTED]
   the SSE fallback (share a helper with `auth.py`).
4. R2 (optional): route hot-path verify failure through `_verify_effect`;
   INDETERMINATE stays VERIFYING instead of VERIFY_FAILED.

## Risks

- Racing-tree hazard is REAL this cycle: the file under review changed between
  reads. Future reviewers must cite committed blobs, as done here.
- R1 becomes a live safety bug the moment `register_github()` is called in prod;
  gate registration on the fix (offsec F-05 + arch §4 watch items already point
  at the wiring step — add R1 to that gate list).
- `?token=` fallback stays live until the V2-02 web migration lands and is
  verified; removal before that breaks the committed web client's live view.

## Confidence

- HIGH on D1 (exact committed lines, unchanged by the diff), C1/C2 (diff +
  committed web source), R3/R4/R5 (committed lines), test counts (both suites
  actually executed and quoted verbatim), dead-code carry-overs (committed-wide
  `git grep`).
- HIGH on R1 as a code interaction (both sides read at committed lines); MEDIUM
  on its blast radius (unregistered connector — impact is future, and demo
  connectors raise cleanly today).
- MEDIUM on "no other regressions": full-file reads of the five touched sources,
  but no live API reproduction (mandate is review; redteam already live-proved
  the adjacent behaviors on an equivalent tree).

## Next task

- Owner of the GitHub wiring step: fix R1 + add the INDETERMINATE test, then
  proceed with repo-allowlist/credential scoping (offsec F-05).
- Whoever owns routes: D1 cancel hardening (issue 2) + R3 one-liner (issue 3).
- V2-02 QA: re-run the quoted suites post-merge; keep the committed-vs-dirty
  discipline while the tree races.
