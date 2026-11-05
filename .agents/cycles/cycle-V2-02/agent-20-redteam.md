# AGENT-20 — Red-Team Audit, REVERSA V2 cycle 2

Hostile review of V2-02 work + remaining V1 overstatements. Every citation
was read with tools before being written. Live reproductions ran against a
LOCAL stack (own uvicorn, temp data dir, port 18231); prod was never
touched. Nothing below invents a result.

## Verdict up front

V2-02 backend work SURVIVES hostile reproduction: the Recovery Manifest is
honest and read-only (live-proven), F2 cross-run aliasing is FIXED
(live-proven), F5 readiness is FIXED, Vultr metering (U26) is now real
code, and the suite is 137 passed / 2 honest skips. No new unverified
claims were found in code comments or the recovery UI (all correctly
hedged). BUT: the two highest-severity V1 code items (R1 GitHub
verify-conflates-error, D1 cancel bypass) are still present verbatim, the
docs overstatements U1–U10 are almost entirely UNFIXED (including a
word-for-word repeat of U7 in a brand-new file), the verification matrix
is now wildly stale (says "19/19" vs 137 green), and the RPE spec's own
header contradicts reality ("No implementation in this cycle" while the
implementation is live). One new suspicious-but-cleared item: a
token-named orphan file in repo root (not a credential, remove before RC).

## Live reproduction (local API, port 18231, fresh temp data dir)

Happy path — intent → approve → execute, then manifest:

- `COMPLETED`, manifest `200 VERIFIED` rule `C6`, chain valid, 59 events.
- Read-only PROVEN: event count 59 before and 59 after manifest fetch.
- Summary 10/10 restored, 0 compensations; 8 created_resources (validate +
  core check carry none — corroborates the U6 read-only-steps point),
  10 final_resources.
- Non-terminal manifest → `409 R4_NOT_TERMINAL`; unknown wf → `404`;
  cancelled wf → `409 R5_CANCELLED_RUN` (all three refusal codes live).

Chaos path — billing `http500` ×5 → intent → approve → execute, then manifest:

- `COMPENSATED`, manifest `VERIFIED_WITH_COMPENSATION` rule `C5`,
  `compensations_run: 7`, 0 divergences.
- F2 FIXED live: after the chaos run compensated, org listing shows
  `acme/active` (happy run's row intact) + `acme/archived` (chaos run's
  own row). In V1 both runs shared one row and the happy run's effects
  were destroyed.

Cancel probe: cancel on READY wf → `CANCELLED`, all actions `SKIPPED`
(D1 bypass itself is a code-path issue, not visible in this output).

## V2-02 work under hostile review

RPE Recovery Manifest (`reversa/apps/api/src/reversa_api/routes/recovery.py`,
755 lines, read in full + `tests/test_recovery_manifest.py` 10 tests read):

- Observed-vs-claimed HONEST. Module docstring claims read-only
  (`recovery.py:7-12`) — true: only SELECTs + `DemoStore` reads, and the
  live 59→59 check proves no event append. Downgrade-only use of live
  rows (`recovery.py:11-12`) matches the code (every live read can only
  flip PRESENT→divergence or add UNKNOWN, never invent a proof).
- Spec-truncation disclosure (`recovery.py:3-5`) is accurate: the repo
  spec file really is truncated mid-§4.3 (verified: file ends at
  "Billing-500 chaos run ... →" with a `[truncated 6268 chars]` marker),
  and the two refusal codes R4/R5 are documented inline (`recovery.py:700-712`).
- C0–C7 implementation matches spec §4.2 order (C0 chain → C1 unknown →
  C2 self-check → C3 manual → C4 exhausted → C5/C6 clean → C7
  fallthrough), `recovery.py:597-623`.
- Challenge attempts that did NOT break it: ref-less VERIFIED steps resolve
  PRESENT-by-record (`recovery.py:402-404`) — tension with spec §2.3 "no
  verify record ⟹ UNKNOWN", but the VERIFIED *transition* attests a passed
  verify() call and every ref-carrying step gets a live store re-check, so
  this is defensible (recommend a one-line spec note, N7). Certain-failure
  FAILED → ABSENT → RESTORED (`recovery.py:443-447`) is guarded by both
  the SUCCEEDED/VERIFYING/UNKNOWN trail check and the uncertainty-marker
  scan (`recovery.py:51-54`); `CHAOS_HTTP500` carries no marker, correctly.
- Nit: `recovery.py:618-620` second `all_restored and not comp_started`
  branch is unreachable (first match at 615 wins) — dead code, cosmetic.
- Note: workflow-level `FAILED` is declared terminal but NO engine path
  transitions a workflow to it (all `_transition_wf` calls enumerated in
  `engine/saga.py`: RUNNING/RETRYING/COMPENSATING/VERIFYING/COMPLETED/
  MANUAL_REQUIRED/PARTIALLY_COMPENSATED/COMPENSATED only). The RPE's
  FAILED-workflow handling is therefore currently unreachable — fail-safe
  direction, but do not claim FAILED-workflow coverage (N8).

F2 run scoping: `_ctx` carries `workflow_id` (`engine/saga.py:208-214`),
`DemoStore` create/find/list/get_by_name all scope on it
(`connectors/services.py:71-147,231-242`), demo-resources route exposes an
org-scoped `workflow_id` filter (`services.py:658-673`), 3 tests green,
live-proven above. FIXED. (`DemoStore.get` is PK-only unscoped,
`services.py:93-99`, but refs are server-written autoincrement ids, so no
cross-org misread is reachable — hardening note only.)

F5 readiness: `/health*` 200/503 + `/readyz` with `ready` flag
(`routes/health.py:25-45`), 5 tests incl. simulated DB-down 503s. FIXED.
RUNBOOK documents the contract (`RUNBOOK.md:23-33`) accurately.

U26 metering: `planner/vultr.py` now populates `PlanResult.usage`
(prompt/completion tokens, model_requested/returned,
model_substituted) with metered errors (`vultr.py:107-164`) + 6 offline
scripted-factory tests. `docs/jury/05-ai-integration.md:12-13` "usage
metering" claim is NOW true. FIXED in code (doc was premature in V1).

U21 literal-timeout: `test_unknown_outcome_reconciles_to_failed_then_retries`
uses literal `"fault": "timeout"` (`tests/test_engine_units.py:122-146`).
CLOSED.

CLI strict verify: 14 tests pin prefix-consistency semantics, truncation
blindness of default mode, ts-rewrite limits, fail-closed strict anchors;
README + jury-04 updated with the exact semantics (diff verified). Honest.

Guest sessions + rate limits: `auth.py:122-406` (in-memory guest store,
TTL 60 min, lifetime quotas via durable `created_by=guest:` rows —
`created_by=org.actor` wiring confirmed at `routes/workflows.py:87`),
`ratelimit.py` (intents 30/min, execute 10/min, keyed by credential hash
or IP). Single-process limitation disclosed in both modules
(`auth.py:127`, `ratelimit.py:8`). 12 guest/rotation/ratelimit tests
green. Design-doc hourly tiers (`docs/security/token-rotation.md:93-98`)
remain design-only and are claimed nowhere else (sweep confirmed) — OK.

GitHub allowlist/registration: doc updated honestly to "32 offline tests
+ 1 live test skipping honestly" (`docs/product/github-connector.md`,
diff verified); skip reason verified live
(`test_github_contract.py:459`). BUT R1 UNFIXED (see Issues).

Web: `?token=` fully migrated to tickets (`EventTimeline.tsx:35-38`,
`TimeMachine.tsx:63-66`; only remaining `?token=` hit is an explanatory
comment at `EventTimeline.tsx:30-31`). New Recovery Race / Time Machine /
Decision Inspector components are honestly hedged in-code ("nothing is
synthesized", "No generated text", "verbatim API event"). No new
unverified UI claims. Other web diffs are error-handling/table-wrap UX
fixes (demo-lab, evidence, settings, recovery pages — diffs read).

v2-clips: 10 files + shot-log; S5 numbers (order [8,7,5,4,3,2,1], 81
events, chain VALID) match my independent live run; secret scan clean
(no `rev_*`/Bearer/key material); shot-log honestly labels screen
recordings/VO/ffmpeg PENDING and keeps published jury numbers unchanged.
Capture script itself is ephemeral (`$env:TEMP`, not committed) so the
"Reproduce" block is not independently verifiable — noted, not a fail.

Competition re-check (`docs/product/competition-v2.md` cycle-2 section):
rival claims explicitly labeled "as described on their public pages,
unverified by us". Honest. Matrix "Tri-state recovery verdict YES" for
REVERSA is now true (RPE landed).

## Remaining V1 overstatements — re-checked on the CURRENT tree

STILL FALSE/UNFIXED (re-verified this cycle, docs untouched):

- U1: "16-field action contracts" (`docs/jury/03-architecture.md:20-21`).
  Still 13 fields (`connectors/sdk.py:19-31`, counted this cycle).
- U2: external-refusal → MANUAL_REQUIRED (`docs/jury/06:15-16`). Wording
  unchanged; engine still yields COMPENSATION_FAILED → retries →
  PARTIALLY_COMPENSATED (V2-01 cite, code paths untouched per agent-01).
- U3: "incident report" (`docs/jury/01:14`, `docs/jury/09:15`,
  `lablab-submission.md:30`). Still no such artifact; web has only an
  "Incidents & recoveries" list heading (`app/page.tsx:37`) and ROI
  variable names. Rename to evidence timeline before the pitch.
- U4: "SSRF verified" (`.agents/verification-matrix.md:17`). Matrix file
  byte-unchanged; still vacuous.
- U5: "timeouts" as implemented control (`docs/jury/06:8`). Unchanged;
  contract `timeout_s` still unenforced by the engine (only Vultr httpx).
- U7: refused-by-design 3-item list (`docs/jury/06:22-23`). RE-VERIFIED:
  zero mass-send/third-party/bulk-send guards in `apps/api/src` (sweep
  this cycle). Only `no_real_payment` exists. AND NOW PROPAGATED to a new
  file: `docs/product/pilot-offer.md:40` repeats "(real payments, mass
  sends, third-party accounts) refuse by design" — must fix (N1).
- U8: "via API+cURL (see README)" (`docs/jury/09:21`). README (read in
  full this cycle) still contains zero curl examples.
- U9: test counts. README:69 still says "19 passed"; matrix says
  "19/19" and "20 pytest + 1 skip" — actual is **137 passed, 2 skipped**.
  Both stale AND mutually inconsistent (as in V1, now worse).
- U10: "deps MIT/BSD (... Caddy images)" (`docs/jury/10:11-12`). Unchanged.
- U19: "no copied code" (`docs/jury/10:11`). Unchanged, still unattested.
- U13/U14/U15: reboot/model-list/spend — still zero committed artifacts
  (`docs/jury/05:15` "35 models" unchanged; v2-clips are honestly-labeled
  LOCAL captures, not prod evidence).
- U12 bench: still no raw committed JSON, but `docs/benchmarks/results.md`
  keeps an explicit "NOT claimed" section (no concurrency/load/inference
  claims) and the bench metric itself is strict — downgraded to "assert
  with stated limits", still one "prove it" question.
- D5 (invoice_issued): still read-once (`services.py:528`), zero writers
  src+tests-wide (sweep this cycle) — CM-13 still untestable as designed.

NOT re-verified this cycle (unchanged per V2-01/agent-01, no V2-02 diff
evidence either way): F4 double-execute race, F7 unbounded duration, U11
lint wording, U16 one-shot qualifier, U18 /roi omission, U22 boot test
(absent — resume route is tested, process boot is not), U23 mp4 duration,
U24 browser E2E, U25 reversa-core store. U20 web labeling: new pages add
no labeling claims; no browser run.

## Bugs re-confirmed (file:line on the CURRENT tree)

- R1 [HIGH, still live-latent]: `GithubConnector.verify()` returns
  `False` on token/transport errors (`connectors/github.py:371-386`:
  373-374 token, 385-386 transport, 378-381 missing ref/allowlist) while
  `_verify_effect` maps clean `False` to ABSENT_CONFIRMED. A GitHub
  outage at reconcile would read as "confirmed absent" → FAILED + retry.
  Gate `register_github()` on the fix (propagate `ConnectorError`).
- D1 [still present]: cancel assigns `action.state` directly
  (`routes/workflows.py:246-248`), bypassing `check_action_transition`
  and `_transition_act` journaling; in-flight actions still freeze under
  terminal CANCELLED (`workflows.py:241-244` only covers
  PENDING/RETRY_SCHEDULED).
- F3 [still present]: `_consume_chaos` takes `.first()` by rule id and
  `return`s on `target_action` mismatch (`engine/saga.py:181-194`) — a
  second rule for another action on the same connector silently never
  fires. CM-11 documents only single-rule mismatch behavior; multi-rule
  shadowing stays a latent bug.
- F6 [removal-ready]: `?token=` fallback still live
  (`routes/workflows.py:349-356`, case-sensitive `removeprefix` at 355)
  though no web caller uses it anymore. Schedule removal + shared ticket
  store before multi-worker.

## New issues in V2-02 (N-series)

- N1 [doc overstatement, NEW FILE]: `docs/product/pilot-offer.md:40`
  repeats U7. Rest of the file is exemplary (number ledger, MEASURED vs
  HYPOTHETICAL labels). One-line fix + re-grep for "mass sends".
- N2 [stale spec header]: `docs/product/recovery-proof-engine.md:3,6`
  says "No implementation in this cycle" / "no API changes" — the RPE +
  `GET .../recovery-manifest` ARE the implementation. Update status to
  IMPLEMENTED (v1); the normative sections themselves held up.
- N3 [stale matrix, under-claiming]: `docs/benchmarks/chaos-matrix-v2.md`
  still marks CM-03/04/05/09/10 MISSING with tally "Covered: 5/20" —
  all five now have tests (`tests/test_chaos_matrix.py`, 5/5 green).
  Update to 10/20.
- N4 [nit]: unreachable `elif` in `routes/recovery.py:618-620`.
- N5 [hygiene, CLEARED as non-secret]: `rev_jury_3B65...TREn` in repo
  root — 57 bytes, unignored, untracked, zero references repo-wide, name
  looks token-like. Shape-checked WITHOUT printing contents: single line,
  starts with a (nonexistent) local Windows path, not credential-shaped.
  Not a leak — but delete before RC; the filename alone will alarm
  scanners and jurors, and G3 must confirm it never gets committed.
- N6: `verification-matrix.md` is the biggest remaining doc liability:
  "pytest 19/19", "20 pytest + 1 skip", "7 tests sécu", "SSRF verified"
  — every number predates V2 (actual: 137/2, 18 security tests alone).
  Rewrite or mark superseded before jury review.
- N7/N8: RPE notes recorded above (ref-less PRESENT rationale deserves a
  spec line; workflow-FAILED branch unreachable — fail-safe, don't claim).
- N10 [process]: racing tree continues — storyboard/competition/pilot/
  clips landed DURING this audit; `health.py`+`test_health.py` staged,
  everything else unstaged (agent-14 I2 still true); `git status` shows
  54 entries. Re-run the suite immediately before RC tagging and confirm
  the commit set (incl. deleting N5, excluding temp files).

## Secrets scan

- RC-diff pattern scan (api_key/secret/token/password/`rev_demo_*`/ghp_) —
  clean. v2-clips secret scan — clean. No `.env` anywhere in repo
  (`git ls-files` + filesystem). No creds in env (8 vars checked, all
  unset — both pytest skips therefore honest). N5 file verified
  non-credential without exposing contents. No secrets committed, none
  printed in this report.

## Structured report

- identity: AGENT-20, Red-Team Auditor, REVERSA V2 cycle 2.
- mandate: hostile review of V2-02 work + remaining V1 overstatements;
  reproduce failures, challenge Recovery Manifest honesty (observed vs
  claimed), verify no new unverified claims in code/docs; read-only
  except this file; cite file:line; run touched tests with
  `reversa/apps/api/.venv` pytest and quote real counts.
- files read (38+): `.agents/cycles/cycle-V2-02/{agent-01,agent-10,
  agent-11,agent-14}.md`, `cycle-V2-01/agent-20-redteam.md`,
  `verification-matrix.md`, `release-gates.md`, `README.md`,
  `docs/jury/{03,05,06,09,10}` (targeted) + `04`/`github-connector`/
  `storyboard`/`competition-v2` diffs, `docs/product/
  {recovery-proof-engine.md (full), pilot-offer.md (full)}`,
  `docs/security/token-rotation.md` (full),
  `docs/benchmarks/{chaos-matrix-v2.md (full), results.md}`,
  `docs/jury/v2-clips/{shot-log.md, s5-recovery.json, s6-cli-verify.txt}`,
  `reversa/infrastructure/RUNBOOK.md`,
  API src: `routes/{recovery.py (full 755 lines), workflows.py:195-254
  + SSE block, health.py (full), guest_sessions.py (index)}`,
  `auth.py` (full 406 lines), `ratelimit.py` (full),
  `engine/saga.py` (targeted: ctx, chaos, transitions, resume),
  `connectors/{github.py verify block, services.py DemoStore}`,
  `planner/vultr.py` (metering block), `connectors/sdk.py`
  (ActionContract), `routes/workflows.py:87` (created_by wiring);
  web: `recovery-race`, `time-machine`, `Recovery/{RaceComparison,
  TimeMachine, DecisionInspector, recovery-utils}` (full),
  `EventTimeline.tsx` (stream block), settings/evidence/demo-lab/
  recovery diffs; tests: `test_recovery_manifest.py`,
  `test_chaos_matrix.py`, `test_demo_isolation.py`, `test_health.py`
  (full), `conftest.py` (full), `test_ai_eval.py`/`test_engine_units.py`
  diffs (targeted), perf/cli/guest test-name sweeps.
- files modified: `.agents/cycles/cycle-V2-02/agent-20-redteam.md` (this
  file) ONLY. Scratch: local server data dir + probe script under
  `%TEMP%` (server stopped; token redacted, never logged here).
- commands run:
  - `pytest reversa/apps/api/tests -q --tb=short -p no:cacheprovider` →
    **137 passed, 2 skipped** in 40.28 s (matches agent-14 run 9).
  - `pytest test_github_contract.py test_ai_eval.py -q -rs` → 39 passed,
    2 skipped with honest reasons (no token/repo; vultr unconfigured).
  - Live probes (`%TEMP%/a20_probes.py`, own uvicorn :18231, temp data
    dir): happy COMPLETED + VERIFIED/C6/59 events + 59→59 read-only;
    R4/R5/404 refusals; chaos COMPENSATED + VWC/C5/7 comps; F2
    active+archived orgs; cancel CANCELLED/SKIPPED. All quoted above.
  - Sweeps: jury-overstatement phrases; `?token=` in web (1 comment
    hit); `rev_jury` refs (none); mass-send/third-party guards (none);
    `invoice_issued` (1 read, 0 writers); ActionContract fields (13);
    `_transition_wf` inventory (no FAILED); docs-diff review; RC-diff
    + clips secret scans (clean); env cred check (8 unset); N5
    shape-checks (len/prefix/exists — contents never printed).
- observed results: RPE honest + read-only live; F2/F5/U26/U21 fixed
  live; R1/D1/F3/F6-code still present; U1-U10 docs still false/stale;
  N1 (pilot U7 repeat), N2 (spec header), N3 (matrix tally), N5 (orphan
  file, non-secret), N6 (matrix rewrite needed); no new code-claim
  violations; secrets clean.
- tests: existing suite 137+2 green (covers manifest C0–C7 incl. tamper
  and divergence, F2 isolation, health 503s, guest/rotation/ratelimit,
  chaos CM-03/04/05/09/10, CLI strict, Vultr metering, resume paths,
  allowlist/registration). NOT re-run: browser E2E (needs Chrome),
  bench vs prod (needs token), mp4 duration. Gaps unchanged: no
  MANUAL_REQUIRED e2e (CM-15), no process-boot test, no
  `/connectors*` tests, CM-06/07/11-14/16-18 still missing.
- issues: R1 HIGH (github verify), D1 (cancel), F3 (chaos shadow), F6
  (fallback removal-ready); N1–N6 above; V1 U1–U10/U13–U15/U19 docs
  still open (U4/U9 worst — matrix rewrite); U11/U16/U18/U22–U25 not
  re-verified.
- risks: (1) R1 becomes a live safety bug at `register_github()` wiring;
  (2) a juror grepping U1/U7/SSRF/curl wording or asking for the
  "incident report"/raw bench JSON still finds gaps behind confident
  prose — N6+U-wording fixes are the cheapest jury-risk reduction left;
  (3) racing-tree + 54-entry dirty status + N5 orphan threaten RC
  hygiene; (4) in-memory stores ×3 (tickets/guests/ratelimit) silently
  break on multi-worker (all disclosed in-code; keep it that way).
- confidence: HIGH on RPE honesty + F2/F5 fixes (live bytes + full
  reads); HIGH on test counts (executed, quoted verbatim); HIGH on
  R1/D1/F3/U1/U7/D5 (exact current lines/sweeps); HIGH on N5
  non-credential (shape-verified); MEDIUM on docs completeness (targeted
  greps + full reads of new/changed docs, not every jury line);
  LOW on prod behavior (never touched — local only by mandate).
- next task: (1) fix R1 + add INDETERMINATE test BEFORE any github
  registration; (2) fix N1 wording + U1/U2/U3/U7/U8/U9/U10 one-liners +
  N2/N3/N6 doc updates (single docs pass); (3) delete N5 orphan, confirm
  RC commit set, re-run full suite at tag time; (4) schedule `?token=`
  removal + D1 cancel hardening + F3 multi-rule scan; (5) prod deploy,
  then re-probe (anon demo reads, manifest on prod runs, E2E + bench
  with human-provided token).
