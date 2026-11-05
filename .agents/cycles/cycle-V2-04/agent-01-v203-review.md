# AGENT-01 — V2-03 merged-diff review (REVERSA V2 cycle 4, FINAL ASCENT)

- Identity: AGENT-01, Architect.
- Mandate: read-only audit of the merged V2-03 diff (commit `f777543`,
  "Jury Mode, F3/F4, 30-case AI eval, CM 13/20, CI gates, video V2,
  404-sniff+CLI fixes") for regressions and layering violations.
  Base `3fad9e4` (V2-02) → `f777543` (V2-03). Only file this agent
  writes: this report.
- Verdict: **APPROVE — no regressions, no layering violations.**
  All findings below are minor follow-ups, none blocking.

## Files read (all before citing)

Source diff (`git diff 3fad9e4..f777543`, full text inspected):

- `reversa/apps/api/src/reversa_api/cli.py` (full file)
- `reversa/apps/api/src/reversa_api/connectors/github.py` (lines 300–419)
- `reversa/apps/api/src/reversa_api/connectors/sdk.py` (full file)
- `reversa/apps/api/src/reversa_api/engine/saga.py` (full file, F3 hunk + callers)
- `reversa/apps/api/src/reversa_api/evidence.py` (full file)
- `reversa/apps/api/src/reversa_api/ratelimit.py` (full file)
- `reversa/apps/api/src/reversa_api/routes/evidence.py` (full file)
- `reversa/apps/api/src/reversa_api/routes/recovery.py` (full file incl. lines 700–756)
- `reversa/apps/web/components/JuryLaunch.tsx` (full file, new)
- `reversa/apps/web/lib/api.ts` (full file)
- `reversa/apps/web/components/Nav.tsx`, `reversa/apps/web/app/page.tsx`,
  `reversa/apps/web/app/workflows/[id]/page.tsx` (diff hunks)
- `.github/workflows/ci.yml` (full file)
- `reversa/apps/api/src/reversa_api/models.py` (ChaosRule, lines 134–144)
- `CHANGELOG.md` (V2-03 entry, lines 1–53)

Test diffs (hunsk inspected):

- `test_cli_verify.py`, `test_github_contract.py`, `test_engine_units.py`
  (F3 tests), `test_perf_regressions.py` (F4 test),
  `test_connectors_routes.py` (new, full), `test_negative_matrix.py`
  (headers/sections), `test_guest_sessions.py` (ratelimit hunks via search)

Existence checks: `reversa/apps/web/app/{recovery-race,time-machine}`,
`reversa/apps/web/components/Recovery/DecisionInspector.tsx`,
`reversa/apps/api/Dockerfile`, `reversa/apps/web/Dockerfile` — all present.

## Files modified

- `.agents/cycles/cycle-V2-04/agent-01-v203-review.md` (this report; only write).

## Commands run (all read-only / local)

1. `git log --oneline -20`, `git status --short` (clean), branch `main`.
2. `git show --stat f777543` — 46 files, +3391/−110.
3. `git diff 3fad9e4..f777543 -- <src + ci + web files>` — full source diff.
4. `git diff 3fad9e4..f777543 --stat -- reversa/apps/api/tests/` — 9 test files.
5. Search: no remaining `" 404 "` / `in str(exc)` sniff in
   `reversa/apps/api/src`; `status_code` only in github.py/sdk.py (+FastAPI
   `status_code=` kwargs, unrelated); `apiAs`/`reversa_guest` only in
   `JuryLaunch.tsx` + `lib/api.ts`; `verify_chain_rows` used only by
   `routes/evidence.py`, `verify_chain` still used by `routes/recovery.py`.
6. `reversa/apps/api/.venv/Scripts/python.exe -m pytest
   tests/test_cli_verify.py tests/test_github_contract.py
   tests/test_engine_units.py tests/test_perf_regressions.py
   tests/test_connectors_routes.py -q` → **83 passed, 1 skipped**.
7. `reversa/apps/api/.venv/Scripts/python.exe -m pytest tests -q` →
   **204 passed, 2 skipped, 1 warning in 55.18s** (warning: standing
   Starlette/httpx TestClient deprecation, pre-existing).
8. `npm run --prefix reversa/apps/web lint` (runs `tsc --noEmit`) → clean.
9. Secrets-scan replication on committed tree:
   `git grep -El '<ci.yml pattern>' -- . ':!ci.yml'` → exit 1, no matches.
10. No SSH, no prod contact; all probes localhost/filesystem only.

## Observed results per change

1. **F3 chaos precedence** (`engine/saga.py`): matching predicate
   (`target_action == "" OR NULL OR exact`) moved into the SQL query with
   `ORDER BY id`, so the lowest-id *matching* rule fires and mismatches
   consume no budget. Correct; 2 dedicated tests pass. Note: the column is
   `NOT NULL DEFAULT ""`, so the `is_(None)` arm is defensive-only — harmless.
2. **F4 evidence single-pass** (`evidence.py`, `routes/evidence.py`):
   `verify_chain_rows()` is the exact loop from `verify_chain`, which now
   delegates to it; the export route passes its already-fetched
   seq-ordered rows (identical SELECT). F4 test proves equivalence incl.
   tamper case, asserts 1 `SELECT ... FROM events` for JSON and HTML, and
   re-verifies the bundle via the CLI. Byte-identical output claim holds.
3. **404-sniff fix** (`connectors/sdk.py`, `connectors/github.py`):
   `ConnectorError.status_code` (default `None`, backward compatible);
   `verify()` returns False only on `GITHUB_API_ERROR` + structured 404.
   No substring-sniff remains in src. 403-with-"404"-body test passes.
4. **CLI hardening** (`cli.py`): non-dict bundles, non-list events,
   missing `workflow.id`, non-dict events, per-event KeyError/TypeError,
   and file/read/JSON errors all return INVALID (exit 1), never traceback.
   Strict-mode semantics unchanged (either anchor suffices). 3 new tests pass.
5. **Ratelimit hardening** (`ratelimit.py`): trailing-slash normalization,
   10k window cap (expired-first, then oldest), unknown-tier fail-open,
   clamped limit/window, guaranteed-positive `Retry-After`. All covered by
   `test_guest_sessions.py` additions. No behavior change for normal traffic.
6. **Jury Mode** (`JuryLaunch.tsx`, `apiAs`): `api()` delegates to `apiAs`
   with the ambient token (backward compatible); `apiAs` used only by
   JuryLaunch. Guest credential kept in separate `reversa_guest_*` keys —
   owner token never replaced. Per-phase states + honest guest/mint errors.
   `tsc --noEmit` clean.
7. **Nav + DecisionInspector card**: `/recovery-race`, `/time-machine`, and
   `Recovery/DecisionInspector.tsx` all exist — no dead links/imports.
8. **CI gates** (`ci.yml`): docker build job (both Dockerfiles exist, no
   push) + secrets-scan (20+ char body, PEM headers, filenames-only output,
   `ci.yml` self-excluded with documented rationale). Local replication:
   committed tree clean.
9. **`routes/recovery.py`**: docstring-only change; endpoint logic untouched,
   read-only posture intact (SELECTs only).
10. **Tests-only additions** (negative matrix 30, connectors routes 6, chaos
    matrix +3, AI eval +4, guest/ratelimit +11): no src changes hidden in
    test files; no new fixtures leak secrets (scan clean).

## Layering check (imports inspected, no violations)

- `routes/evidence.py` → `evidence`, `models`, `auth` only. No engine or
  connector imports. Clean.
- `routes/recovery.py` → `auth`, `connectors.services` (DemoStore read
  probe), `engine.saga.WF_TERMINAL` (constant only), `evidence.verify_chain`,
  `models`. Read-only; the saga import is a terminal-state constant, not an
  execution path, and pre-exists V2-03 (diff was docstring-only). Clean.
- `engine/saga.py` → `config`, `connectors.sdk`, `evidence`, `models`,
  `.states`. No route/auth/web imports; V2-03 added only `sqlalchemy.or_`.
  Clean.
- `cli.py` → `evidence` (`GENESIS`, `canonical_bytes`) only. Offline, no
  DB/network imports. Clean.
- `connectors/{sdk,github}.py`: `status_code` is pure data, no new deps.
  Clean.
- Web `apiAs`/`JuryLaunch`: pure fetch helper + component using
  `api`/`apiAs`/`getToken` only. Clean.

## Issues (minor follow-ups, none blocking, none introduced as regressions)

- F1 (cosmetic, pre-existing): when the server-side chain verdict is false,
  the CLI prints `VALID: ...` then `INVALID: server-side chain verdict is
  false`. Exit code is correct (1); the dual line could confuse naive
  output parsers. V2-03 only hardened the lookup, behavior unchanged.
- F2 (perf follow-up, not a regression): the recovery-manifest endpoint
  still issues 3 event SELECTs (dict fetch + `verify_chain` + head hash).
  F4 scoped to the evidence export; a rows-reuse pass could follow later.
- F3 (hygiene): JuryLaunch leaves the guest credential in localStorage
  after expiry; no cleanup/expiry check on load. Minor.
- F4 (accepted tradeoff): ratelimit eviction sorts the window dict under
  the lock per request while over cap — O(n log n) at n ≤ ~10k under
  active attack only. Bounded and acceptable.
- F5 (accepted tradeoff): secrets-scan by design misses short bodies
  (<20 chars) and self-excludes `ci.yml`. Documented in the job comments.

## Risks

- No merge/regression risk identified: full suite (204 passed, 2 skipped)
  reproduces the CHANGELOG claim exactly on this tree; touched subset
  (83/1), web typecheck, and secrets-scan all green.
- Jury Mode touches no authz logic (it only drives existing endpoints as a
  quota-bound guest); blast radius is one new component + one helper.
- No migration, no config, no prod interaction in this diff.

## Tests

- Full API suite via project venv: **204 passed, 2 skipped** (matches
  CHANGELOG V2-03 "VERIFIED" count; same 2 standing conditional skips).
- Touched-area subset (cli, github, engine, perf, connectors routes):
  **83 passed, 1 skipped**.
- Web `lint` (`tsc --noEmit`): clean.
- Secrets-scan replicated locally on committed tree: clean.

## Confidence

High. Every src hunk was read, every claim above is grounded in inspected
files or executed commands; counts are quoted from real runs in this session.

## Next task

Hand to AGENT-02 (or cycle-4 implementer): proceed with FINAL ASCENT scope
on top of clean `f2a6152`; optional follow-ups F1–F3 are safe to defer
past the ascent unless a jury-facing parser consumes CLI stdout (then do F1).
