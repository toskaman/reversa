# AGENT-05 — GitHub Auditor (REVERSA V2 cycle 4, FINAL ASCENT)

## Identity

- Agent: AGENT-05, GitHub Auditor
- Cycle: REVERSA V2-04 (FINAL ASCENT)
- Base: committed tree clean at V2-03 merge (`f2a6152`); pre-existing worktree
  modifications in `reversa/apps/web` only (globals.css, layout.tsx), untouched by this audit.

## Mandate

Verify the R1 + structured-404 fixes by reading code and running
`tests/test_github_contract.py`, quoting real counts. Confirm registration
stays conditional and the live test skips honestly. No live calls, no code
changes.

## Files read (no files modified)

1. `reversa/apps/api/src/reversa_api/connectors/github.py` (563 lines, full read)
   - R1 `verify()`: returns `False` ONLY on structured `GITHUB_API_ERROR` with
     `status_code == 404` (lines 399-404); every other error path raises
     `ConnectorError` (missing token, `GITHUB_VERIFY_UNVERIFIABLE` on
     unreadable refs, allowlist refusal, transport/API failure, `UNKNOWN_ACTION`).
   - Structured-404 (V3-1): `_request()` attaches `status_code` to
     `GITHUB_API_ERROR` (lines 331-336); no message substring-sniffing anywhere
     in the module (verified by reading; the only "404" comment is the V3-1 note).
   - Registration: `registration_decision()` requires token AND non-empty
     allowlist (lines 151-188); `register_github()` raises
     `GITHUB_NOT_CONFIGURED` otherwise (lines 550-563). Module docstring states
     it does NOT self-register.
2. `reversa/apps/api/tests/test_github_contract.py` (549 lines, full read)
   - R1 tests: `test_verify_500_raises_not_false`,
     `test_verify_404_is_genuine_absence`, `test_verify_unknown_action_raises`,
     plus `GITHUB_VERIFY_UNVERIFIABLE` assertion in
     `test_error_messages_never_contain_token`.
   - Structured-404 test: `test_verify_403_mentioning_404_still_raises`
     (403 whose body contains "404" must raise `GITHUB_API_ERROR`, not return False).
   - Live test `test_live_create_label_update_close_cycle` gated by
     `@pytest.mark.skipif(not has_live_config(), reason=LIVE_SKIP)`.
3. `reversa/apps/api/src/reversa_api/connectors/sdk.py` (lines 1-80)
   - `ConnectorError` carries structured `status_code` (V3-1 comment:
     "callers must use this, never substring-sniff the message").
4. `reversa/apps/api/src/reversa_api/connectors/__init__.py` (full read)
   - Imports `sdk` + `services` only and calls `register_all()`; no github
     import, so boot never registers the GitHub connector.
5. `reversa/apps/api/src/reversa_api/main.py` (grep)
   - No `github` reference; only `import reversa_api.connectors` (demo services).

## Commands run

1. `cd reversa/apps/api; .\.venv\Scripts\python.exe -m pytest tests/test_github_contract.py -v`
   (GitHub env vars cleared first; no token in env — confirmed.)
2. `.\.venv\Scripts\python.exe -m pytest tests/test_github_contract.py -rs -q`
   (to capture the exact skip reason.)
3. `git log --oneline -8`, `git status --porcelain` (base/tree check).
4. `Select-String` / ripgrep probes for `register_github`,
   `registration_decision`, `github` imports across `src` (registration-path audit).

## Observed results

- R1 fix VERIFIED in code: `verify()` raises on 500/transport/unreadable-ref/
  unknown-action paths, returns `False` only for structured 404.
- Structured-404 fix VERIFIED in code: absence decision keys on
  `exc.status_code == 404`, never on message text.
- Registration stays conditional VERIFIED: nothing imports
  `reversa_api.connectors.github` outside its own test; boot path
  (`main.py` -> `connectors/__init__.py` -> `register_all()`) registers demo
  services only; `register_github()` enforces token+allowlist itself.
- No live calls made (no token configured; live test skipped).

## Tests

`tests/test_github_contract.py` via `reversa/apps/api/.venv` pytest:

- **36 passed, 1 skipped** (collected 37 items, 0.09s).
- The 1 skip is `test_live_create_label_update_close_cycle` with reason:
  "no GitHub token/test repo in env (or repo not allowlisted); live contract
  test skipped honestly" — honest skip, confirmed by `-rs` output.
- Targeted R1/structured-404 tests all pass:
  `test_verify_500_raises_not_false`, `test_verify_404_is_genuine_absence`,
  `test_verify_403_mentioning_404_still_raises`,
  `test_verify_unknown_action_raises`, `test_error_messages_never_contain_token`.
- Registration tests all pass (4 decision + 2 register cases).
- Warning (pre-existing, unrelated): Starlette `httpx` TestClient deprecation.

## Issues

- None. No failures, no skips beyond the honest live-test skip.

## Risks

- Live path (`test_live_create_label_update_close_cycle`) is unverified in this
  cycle by design (no token, no live calls). It remains covered by the honest
  skip plus full offline MockTransport cycle tests.
- Pre-existing worktree dirt in `reversa/apps/web` (globals.css, layout.tsx)
  is outside this mandate and was not touched.

## Confidence

High. All R1 + structured-404 claims checked against full file reads plus a
green 36-passed/1-honestly-skipped run; conditional registration confirmed at
both the code level (no boot import) and the behavior level (6 registration tests).

## Next task

- AGENT-06 (or cycle lead): proceed with remaining V2-04 FINAL Ascent gates;
  GitHub surface needs no further work unless the live test is scheduled with
  a real test repo + token.
