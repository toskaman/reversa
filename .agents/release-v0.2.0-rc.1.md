# Release DRY RUN — v0.2.0-rc.1 (REVERSA V2 cycle 4, FINAL ASCENT)

- Author: AGENT-17 (Release Engineer)
- Date (UTC): 2026-11-05
- Base commit: `f2a6152` ("CHANGELOG: V2-03 entry (204 verified)"), branch `main`
- Working tree at check time: DIRTY (uncommitted cycle-V2-04 work; see `git status`
  excerpt below). Gate verdicts distinguish **committed base** (CI) from
  **working tree** (local runs).
- Tag `v0.2.0-rc.1`: NOT created (per mandate — dry run only).
- Verdict: **NOT READY — 2 red items** (G1 working-tree failures, G3 gate-script
  bug fails CI on a clean tree). Details per gate below.

## CI status of latest push (read-only `gh`)

- `gh run list --limit 5`: latest run **42063308961** (`f2a6152`, push to main,
  2026-11-05T16:20:00Z) = `completed / failure`. Previous run **42063263160**
  (`f777543`) = `completed / failure`. Runs for V2-02/V2-01 = `success`.
- `gh run view 42063308961 --json jobs`: `docker=success`, `api=success`,
  `web=success`, **`secrets-scan=failure`**.
- `gh run view 42063308961 --log-failed`: the secrets-scan step prints its
  script echo and then only `##[error]Process completed with exit code 1` —
  it emits NEITHER "Secret pattern matches in:" NOR "No secret patterns
  found." (full-log grep confirms no execution output lines).

## G1 — Tests green: RED on working tree / GREEN on committed base

- Committed base: CI `api` job green on both V2-03 pushes (runs 42063263160,
  42063308961). CHANGELOG records 204 passed / 2 skipped / 0 failed on
  `f777543`.
- Working tree (local, `.venv` Python 3.14.4, pytest 9.2.0):
  `reversa/apps/api/.venv/Scripts/python.exe -m pytest reversa/apps/api/tests -q`
  → **3 failed, 251 passed, 2 skipped in 72.16s** (1 standing
  Starlette/httpx `TestClient` deprecation warning).
- Failures (all in uncommitted cycle-4 delta):
  1. `test_guest_sessions.py::test_owner_can_mint_guest_session` —
     `assert 'guest-d18c96d2e9c37290' == 'demo-3a96c9a2'` (guest org slug no
     longer inherits the demo slug).
  2. `test_guest_sessions.py::test_guest_demo_org_only_isolation` —
     `assert 404 == 200` (cross-org workflow read now 404s).
  3. `test_negative_matrix.py::TestEvidenceNegatives::test_evidence_unknown_format_falls_back_to_json`
     — `assert 422 == 200` (`format=xml` now validated instead of falling
     back to JSON).
- Skips: same 2 honest conditional skips (Vultr live-provider eval, GitHub
  live cycle); no secrets in env.
- Gate action: reconcile the 3 failures (update stale tests or revert the
  behavior change) before cutting the RC. No new skips.

## G2 — Build green: GREEN (local) + GREEN (CI); docker local run N/A

- `npm run --prefix reversa/apps/web lint` (`tsc --noEmit`) → exit 0, no errors.
- `npm run --prefix reversa/apps/web build` (Next.js 15.5.29) → exit 0,
  "Compiled successfully", 13/13 static pages (routes `/`, `/command`,
  `/connectors`, `/demo-lab`, `/evidence/[id]`, `/recovery`,
  `/recovery-race`, `/roi`, `/settings`, `/time-machine`,
  `/workflows/[id]`, `/_not-found`, `/icon.svg`).
- `git status -- '*Dockerfile*' '*compose*' '*health*'` → no diffs (Dockerfiles
  unchanged in working tree).
- Local `docker build` NOT run: no `docker` CLI on this host
  (`CommandNotFoundException`). CI `docker` job (api+web image builds, no
  push) green on latest push — quoted as the image-build evidence.
- Note: an earlier `LINT-EXIT=1` reading was a `tail.exe` pipe failure, not
  `tsc`; re-run without the pipe returned exit 0.

## G3 — Secrets scan clean: TREE CLEAN, gate script RED (CI bug)

- Committed base:
  `git grep -E -l -e '(^|[^A-Za-z0-9_])rev_[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{20,}|BEGIN (RSA |DSA |EC |OPENSSH )?PRIVATE KEY' -- . ':!.github/workflows/ci.yml'`
  → no matches, exit 1 (clean).
- Working tree (CI-equivalent `grep -rEl` with the same excludes over `.`) →
  no matches, exit 1 (clean, incl. untracked cycle-V2-04 files).
- `.env` hygiene: `git ls-files reversa/infrastructure/.env
  reversa/apps/api/.env` → untracked; `git check-ignore -v` → both ignored
  by root `.gitignore:9:.env`. Only `reversa/infrastructure/.env.example`
  is tracked. No CI step echoes env (ci.yml inspected).
- **CI bug (root cause of red runs):** `.github/workflows/ci.yml` lines
  51-61 run `SCAN_OUT=$(grep -rEl ...)` under `bash -e` (Actions default,
  confirmed `shell: /usr/bin/bash -e {0}` in logs). When the tree is clean,
  grep exits 1 and the bare assignment trips `errexit`, killing the step
  before `STATUS=$?` — exactly matching the observed silent exit 1. The job
  as written can never pass (clean → silent exit 1; dirty → exit 1 with
  message). Fix (not applied — outside mandate): append `|| true` to the
  assignment or guard with `set +e`/`set -e` around the grep.
- Gate action: fix the gate script, re-run CI to green, then cut the RC.

## G4 — Migrations safe: GREEN ("no migration in this release")

- No Alembic/migration files tracked (`git ls-files | grep -i alembic|
  migration` → empty).
- `git status -- models.py db.py schemas.py` → unmodified; `db.py` last
  touched by committed `3fad9e4` (V2-02). No model changes in the RC delta.
- Declaration: **no migration in this release**.

## G5 — Rollback ready: YELLOW (first RC; backup freshness unverified)

- Previous release tag: NONE — `git tag --list` is empty; `v0.2.0-rc.1`
  would be the first tag, so there is no previous tag/image to keep yet.
- Image tags: `reversa/infrastructure/docker-compose.yml` builds `api`/`web`
  from source with NO `image:` tags (only `postgres:16-alpine` and
  `caddy:2-alpine` are pinned). Per-release tagging is not implemented —
  process gap for G6/Promotion.
- `docker compose config` NOT recorded: no docker CLI on this host.
- Procedures exist and were read: `RUNBOOK.md` Backup (`./scripts/backup.sh`
  → `backups/reversa-<ts>-{postgres.sql.gz,appdata.tgz}`, default 14d
  retention) + Restore (postgres via `psql`, `/data` appdata tarball).
- Prod backup freshness NOT verified: no SSH per mandate (localhost only).
- Gate action: fix G6 tagging, take + verify a fresh backup in the deploy
  window, record `docker compose config` on the deploy host.

## G6 — Version pin: YELLOW (pins consistent, bump + tag pending)

- `reversa/apps/api/src/reversa_api/__init__.py:3`:
  `__version__ = "0.1.0"`.
- `reversa/apps/web/package.json`: `"version": "0.1.0"`, `lint` = `tsc
  --noEmit`. Pins consistent with each other, but still at 0.1.0.
- `/readyz` wiring confirmed: `routes/health.py` `_status()` returns
  `{"status", "version": __version__, "db"}` and `ready()` adds `"ready"`
  with 200/503 honesty — post-deploy version check is supported.
- Pending (NOT done — dry run): bump both to `0.2.0-rc.1`, tag
  `v0.2.0-rc.1`, per-release image tags (see G5 gap), post-deploy
  `/readyz` version assertion.

## Promotion (not executed)

Retag `v0.2.0-rc.1` → `v0.2.0` only after all gates are green on the RC
commit; record backup location + image tags in the release notes; keep
previous working images until promotion.

## Appendix — working-tree status excerpt (2026-11-05)

Modified (tracked): `docs/jury/09-demo-script.md`, `reversa/apps/api/src/
reversa_api/{auth,engine/saga,routes/evidence,routes/guest_sessions,
routes/recovery,routes/workflows}.py`, `reversa/apps/api/tests/
{test_chaos_matrix,test_engine_units,test_recovery_manifest,test_security}.py`,
`reversa/apps/web/app/{globals.css,layout.tsx,page.tsx,recovery-race/page.tsx,
time-machine/page.tsx}`, `reversa/apps/web/components/JuryLaunch.tsx`,
`Recovery/RaceComparison.tsx → Recovery/ExecutionComparison.tsx` (renamed),
`reversa/infrastructure/RUNBOOK.md`. Untracked: `.agents/cycles/cycle-V2-04/`,
`docs/benchmarks/concurrency-results.md`, `test_crash_recovery.py`,
`test_guest_isolation.py`, `Recovery/ManifestPanel.tsx`.
