# AGENT-20 — Red-Team Audit, REVERSA V2 cycle 3

Hostile verification of V2-03 outputs + R1/D1/R3 fix confirmation. Every
citation was read with tools before being written. All repros ran LOCAL
(TestClient + MockTransport + pristine `git archive` extracts); prod was
never touched, no SSH. Nothing below invents a result.

## Verdict up front

R1/D1/R3 HOLD against hostile repro — with ONE live hole: the R1
404-sniff (`connectors/github.py:400`) provably misreads a non-404 error
as absence (403 + `" 404 "` in body → `False`), demonstrated with bytes
below. V2-03 outputs largely SURVIVE: F3, F4, ratelimit hardening,
connectors routes, negative matrix, guest edges, RPE-spec restoration,
github runbook, jury-04 wording, and BOTH CHANGELOG counts (49/2, 143/2
re-verified pristine by me) check out. N1 is FIXED, N2 closed, N5 gone.
New catches: the ai-eval "Keyword" fake does no keyword matching (answer
key, overstated docstring), `verify_bundle` still crashes on malformed
bundles (proven `KeyError`), the chaos-matrix spec drifted further
(10/20 on paper vs 13/20 in tests), the runbook undercounts live-test
API calls (8, not ~6). U1/U2/U3/U5/U7/U8/U10/U19, N6, F6, R4 carry over.

## Local repro: R1/D1/R3 (each reproduced, not just re-read)

Script: `C:\Users\TheBox\AppData\Local\Temp\a20_repro.py` (kept for
re-run; its scratch SQLite dir was deleted after the run).

R1 — `GithubConnector.verify` error-vs-absence (MockTransport):

- 500 → raises `GITHUB_RETRYABLE` (retryable). 404 → `False`. Plain 403
  → raises `GITHUB_API_ERROR`. No token → raises `GITHUB_NO_TOKEN`. All OK.
- HOSTILE: 403 with body `"rate limit error 404 exceeded"` → returned
  `False` (MISREADS as absence → saga `ABSENT_CONFIRMED`). Root cause is
  the sniff `" 404 " in str(exc)` (`connectors/github.py:400`), where
  `str(exc)` embeds `response.text[:300]` (`github.py:331-336`). Any
  non-404 4xx whose body contains `" 404 "` is misread. Narrow trigger,
  exactly the P0-REC-01-forbidden class. Agent-01's nit, now PROVEN live.

D1 — cancel policy (TestClient, isolated temp data dir):

- EXECUTING action → `409 '1 action(s) in flight (seq [1]); resume to
  reconcile, then cancel'`. All 7 policy states (CLAIMED, EXECUTING,
  SUCCEEDED, VERIFYING, UNKNOWN_OUTCOME, COMPENSATION_PENDING,
  COMPENSATING) → 409 each. COMPENSATING workflow → 409
  `'compensation in progress; cannot cancel half-undo'`. All OK.
- Residual VERIFIED/FAILED leftovers under CANCELLED are fail-safe: the
  pump refuses terminal workflows (`engine/saga.py:718-719`, read).

R3 — SSE fallback scheme (TestClient): lowercase `bearer` → 200 +
`event: done`; `BEARER` → 200. OK (`routes/workflows.py:373-378`, read).

## V2-03 outputs under hostile review

SURVIVES (verified by read + execution):

- F3 chaos filter-before-pick (`saga.py:192-200`): `or_(=="" /
  is_(None) / == action)` preserves old wildcard semantics, lowest-id
  wins, mismatch consumes no budget. Both engine tests pin exact fault
  codes both directions + two-sided budget asserts (diff read in full).
- F4 single-pass evidence (`evidence.py:118-122`,
  `routes/evidence.py:30-31`): tuple-equivalence incl. tamper +
  `== 1` SELECT locks on json AND html (diff read in full).
- Ratelimit hardening (`ratelimit.py`, full read): 10k cap +
  purge-then-evict (`:37-52`), trailing-slash norm (`:65-79`),
  unknown-tier fail-open + degenerate clamp (`:93-100`), `Retry-After`
  positive int (`:140`). Matches the 11 c3 tests (diff read in full).
- Connectors routes (6 tests, full read): exact entry key sets, store
  strings, cross-tenant zero-resources on both endpoints.
- Negative matrix (30 tests, full read): exact detail pins, 410→409
  expiry consumption + `approval.expired` event, inflight seq in detail.
- Guest c3 edges: mint-bounds matrix (0/21/0/51/negatives → 422;
  20/50 accepted) matches `GuestMintIn` bounds; sibling-quota isolation.
- RPE spec restoration: all 7 cited test names exist
  (`test_recovery_manifest.py:68,119,138,181,207,234,251`); `R_`
  codes match shipped `routes/recovery.py:535-537`. N2 CLOSED. The
  restored §4.4 pairing table honestly discloses the evaluator never
  branches on `workflow_state` (v1 does not refuse mismatches).
- GitHub runbook (`github-connector.md`): line refs exact
  (`github.py:368-417`, tri-state `saga.py:68-107` confirmed by my read:
  raise → INDETERMINATE `:95-96`, `False` → ABSENT_CONFIRMED `:103-104`);
  `35 passed, 1 skipped` re-executed by me (see Tests); known-gap
  disclosure (no GitHub→INDETERMINATE e2e test) is honest; live-test
  narrative matches `test_live_...:504-535` (title, label, rename,
  `completed` close, `finally` close). "No live calls were made" taken
  at face value — no token exists in this env and the live test skips.
- jury-04 strict wording ("either anchor alone suffices") matches
  `_strict_verdict` (`cli.py:101-118`, each anchor checked
  independently). Holds.
- CHANGELOG.md (NEW file, hostile-checked): V2-01 `49 passed, 2
  skipped` and V2-02 `143 passed, 2 skipped` BOTH re-verified by me on
  pristine `git archive` extracts (see Tests). TO-VERIFY labels honest.
- JuryLaunch.tsx (full read): "60 min" == `GUEST_TTL_SECONDS = 3600`
  (`auth.py:134`); quota-bound (`auth.py:192-200`); "guests cannot mint"
  == `require_demo_owner` (`auth.py:182-189`). Guest credential in
  localStorage (`JuryLaunch.tsx:93`) matches app convention (owner
  token same store) — noted, not a finding.
- DecisionInspector: literal API values or `"not recorded"`
  (`DecisionInspector.tsx:7-15`, verified in render body). Honest.
- N1 FIXED: `pilot-offer.md:44` now states bulk sends /
  third-party-account effects have NO code guard (read pre-sibling-edit;
  file changed again during this audit — see Risks).
- N5 CLOSED: no `rev_jury*` on filesystem; never committed.
- CI secrets-scan: pattern run tree-wide → ZERO hits (would pass).
  Docker jobs unexecuted (no docker here) — NOT verified, only read.

NEW CATCHES (V3-series):

- V3-1 [R1 hole, proven, fix before any live GitHub reconcile]:
  `github.py:400` 404-sniff misread (repro above). Fix: structured
  `status_code` on `ConnectorError`, match exactly; add the
  GitHub-raise→`_verify_effect`→INDETERMINATE integration test.
- V3-2 [misleading test code]: `_KeywordRefusalFake` performs NO
  keyword matching — all three fakes resolve category by exact
  intent-string lookup against CASES (`test_ai_eval.py:213-216`,
  `:234-237`, `:252-253`). The module docstring "prove the eval
  itself discriminates" overstates a mutation-style harness self-test.
  Rename (e.g. `_AnswerKeyRefusalFake`) + soften docstring.
- V3-3 [live crash, agent-01 issue 3 now proven]: `verify_bundle`
  on a prefix-plausible bundle without `workflow` raises
  `KeyError: 'workflow'` (`cli.py:78`, traceback observed) instead of
  `(False, INVALID)`. `main()` calls it unguarded (`cli.py:175`).
  Wrap in a clean INVALID verdict.
- V3-4 [doc drift, N3 expanded]: `chaos-matrix-v2.md` tally says
  10/20 (`:82-85`) with rows MISSING for CM-03/04/05/09/10
  (`:41-43,:52-53`) AND CM-11/13/15 (`:54,:61,:63`) although tests
  exist for all eight (test header: 13/20). The "Missing"
  priority list leads with already-covered CM-11/CM-13.
- V3-5 [nit]: runbook "~6 API calls" for the live test is 8 by my
  count from code (create GET+POST, verify GET, labels POST, update
  GET+PATCH, close PATCH, finally PATCH). "Negligible" verdict holds.
- V3-6 [stale cells]: `token-rotation.md:173` "7 passed" for
  test_security (now 21); `jury/10:9` "Backend suite 19/19".

CARRYOVERS (re-checked on current tree, still open, not regressions):

- U1 `sdk.py:1` "16-field"; U3 "incident report" (`jury/01:14`,
  `jury/09:15`, `lablab-submission.md:30`); U7 refused-by-design
  (`jury/06:22-23`); U9-half (README:69 now correct at 143/2, jury/10
  stale); N6 `verification-matrix.md` ("pytest 19/19", "7 tests sécu",
  "SSRF") vs actual 200/2; F6 `?token=` fallback live
  (`workflows.py:372-378`) though web uses `?ticket=` exclusively
  (`EventTimeline.tsx:38`, only other hit is the comment `:31-32`);
  R4 ticket-pop-before-bind (`workflows.py:336-340`, read).
- NOT re-verified: R2, D5/D7, F7, U2/U5/U8/U10/U11/U16/U18/U19/U22-U25
  (no V2-03 diff evidence either way; agent-01's verdicts stand).

## Secrets scan

- CI-pattern sweep tree-wide (`rev_…{20,}|ghp_…{20,}|PRIVATE KEY`):
  zero hits. No secret material in the V2-03 diffs.
- `reversa/infrastructure/.env` exists (4 lines) but is git-ignored
  (`.gitignore:9`) and untracked; only `.env.example` is committed.
  Values never read.
- Self-note: my repro booted a throwaway stack whose server log
  printed its demo token; the scratch DB was deleted, killing the
  token. No prod/foreign credential was ever used. No secrets
  committed, none printed in this report.

## Structured report

- identity: AGENT-20, Red-Team Auditor, REVERSA V2 cycle 3.
- mandate: hostile verification of V2-03 outputs + confirm R1/D1/R3
  fixes hold (local repro of each); hunt new unverified claims.
  READ-ONLY except this file; cite file:line; run touched tests with
  `reversa/apps/api/.venv` pytest and quote real counts; localhost
  only; no prod SSH; no push; never commit secrets.
- files read (40+): cycle reports `V2-03/{agent-01,agent-11,agent-14}.md`
  + `V2-02/agent-20-redteam.md` (full); `connectors/github.py`
  (verify + _request + _do_* + live test), `routes/workflows.py`
  (cancel + SSE ticket/stream blocks), `ratelimit.py` (full),
  `engine/saga.py` (_verify_effect + _pump + F3 diff), `evidence.py`
  + `routes/evidence.py` (F4 diffs), `cli.py` (full), `auth.py`
  (guest block), `recovery.py:535-537`, `engine` pump guard,
  `conftest.py` (full), tests `test_github_contract.py` (R1 + live
  blocks), `test_security.py:210-303`, `test_connectors_routes.py`
  (full), `test_negative_matrix.py` (full), c3/F3/F4/ai-eval/chaos
  diffs, `test_recovery_manifest.py` (name/code pins);
  `EventTimeline.tsx` (stream block), `JuryLaunch.tsx` (full),
  `DecisionInspector.tsx` (head + render), `lib/api.ts` + page/Nav
  diffs, `.github/workflows/ci.yml` (diff);
  `github-connector.md` + `recovery-proof-engine.md` (diffs),
  `pilot-offer.md:30-54`, `jury/06` (full), `verification-matrix.md`
  (full), `chaos-matrix-v2.md` (tally + rows), `CHANGELOG.md` (full).
- files modified: `.agents/cycles/cycle-V2-03/agent-20-redteam.md`
  (this file) ONLY. Scratch: repro script under `%TEMP%` (kept);
  scratch SQLite dir + pristine archives created then deleted.
- commands run: `git log/status/diff` snapshots; R1/D1/R3 repro
  script (MockTransport + TestClient, isolated temp data dir);
  `test_github_contract.py` → 35 passed, 1 skipped; `test_security.py
  -k "cancel or stream or bearer"` → 10 passed, 11 deselected; FULL
  suite (dirty tree) → 200 passed, 2 skipped, 1 warning in 58.56 s;
  pristine V2-01 (63bb949) → 49 passed, 2 skipped in 55.95 s;
  pristine V2-02 (3fad9e4) → 143 passed, 2 skipped in 73.38 s (both
  pristine runs needed one retry after a transient collection error);
  CLI crash one-liners; tree-wide secret-pattern + overstatement
  sweeps; `.env` tracking/line-count checks (values never read).
- observed results: R1/D1/R3 hold except the proven 404-sniff
  misread; V2-03 code outputs all hold; CHANGELOG counts verified;
  N1/N2/N5 closed; V3-1..V3-6 new; U1/U3/U7/N6/F6/R4 carry over.
- tests: quoted above; zero failures in this session. Skips are the
  two standing honest ones (Vultr unconfigured, no GitHub token).
- issues: V3-1 (404-sniff misread — highest), V3-2 (fake naming +
  docstring overstatement), V3-3 (CLI KeyError crash), V3-4
  (chaos-matrix spec 10/20 vs 13/20), V3-5 (runbook ~6→8), V3-6
  (stale counts), plus carryover U/N/F/R items above.
- risks: (1) V3-1 becomes a live safety bug the moment GitHub
  reconcile runs against a real repo; (2) racing tree — 3 more files
  got dirty DURING this audit (incl. pilot-offer.md, which my N1
  verdict read pre-edit): re-run the suite at tag time and re-confirm
  the commit set; (3) N6 + U-wording remain the cheapest jury-risk
  reduction; (4) in-memory stores ×3 still single-process (disclosed);
  (5) first-attempt pristine-collection errors (transient, both
  retries clean) suggest sibling churn can bite any long run.
- confidence: HIGH on R1/D1/R3 verdicts (bytes, not just reads) and
  on V3-1/V3-3 (proven); HIGH on test counts (executed, quoted
  verbatim, incl. both pristine CHANGELOG numbers); HIGH on V2-03
  code outputs (full diffs read + suite green); HIGH on N1/N2/N5
  (exact lines/absence); MEDIUM on docs completeness (targeted greps
  + full reads of new/changed docs, not every jury line); LOW on prod
  (never touched — localhost-only by mandate; no uvicorn boot this
  audit, TestClient only).
- next task: (1) fix V3-1 (structured status_code + e2e
  INDETERMINATE test) BEFORE any live GitHub reconcile; (2) V3-3 CLI
  guard + V3-2 rename/docstring (small); (3) single docs pass: V3-4
  matrix rewrite (13/20 + row cells), V3-5/V3-6 one-liners, N6 matrix
  rewrite, U1/U3/U7 wording; (4) re-run FULL suite at tag time on the
  exact commit set; (5) deploy, then re-probe prod with agent-11's set.
