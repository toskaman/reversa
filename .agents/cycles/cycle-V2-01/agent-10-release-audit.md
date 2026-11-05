# AGENT-10 — Release / CI / Deploy Audit (REVERSA V2 cycle 1)

## 1. Identity

- Agent: AGENT-10, DevOps Engineer, REVERSA V2 cycle 1
- Date (UTC): 2026-11-05
- Mode: READ-ONLY audit, except this file

## 2. Mandate

Audit `.github/workflows/ci.yml` and deploy scripts: CI gates, rollback,
backup, migration safety. Propose a release-candidate (RC) process.
Never invent test/deployment results. Never commit secrets. No push.
No modifications outside this file.

## 3. Files read (all inspected in full unless noted)

| # | File | Lines | Notes |
|---|------|-------|-------|
| 1 | `.github/workflows/ci.yml` | 27 | Whole CI pipeline |
| 2 | `reversa/infrastructure/docker-compose.yml` | 70 | Prod stack: postgres/api/web/caddy + 4 volumes |
| 3 | `reversa/infrastructure/scripts/deploy.sh` | 8 | Whole deploy procedure |
| 4 | `reversa/infrastructure/scripts/healthcheck.sh` | 14 | Whole post-deploy verify |
| 5 | `reversa/infrastructure/scripts/add_token.py` | 19 | Whole file |
| 6 | `reversa/infrastructure/Caddyfile` | 17 | Whole file |
| 7 | `reversa/infrastructure/.env.example` | 6 | Whole file (placeholder values only) |
| 8 | `reversa/apps/api/Dockerfile` | 8 | Whole file |
| 9 | `reversa/apps/web/Dockerfile` | 17 | Whole file |
| 10 | `reversa/apps/web/next.config.ts` | 7 | Confirms `output: "standalone"` |
| 11 | `reversa/apps/web/package.json` | 22 | `lint` = `tsc --noEmit`, no test script |
| 12 | `reversa/apps/api/pyproject.toml` | 29 | Deps ranges, no lock file, ruff config, no alembic |
| 13 | `reversa/apps/api/src/reversa_api/db.py` | 70 | `create_all`/`checkfirst` schema init, no migrations |
| 14 | `reversa/apps/api/src/reversa_api/models.py` | 162 | 8 tables, naive-UTC convention |
| 15 | `reversa/apps/api/src/reversa_api/main.py` | 70 | Lifespan: init_db, seed demo, reconcile |
| 16 | `reversa/apps/api/src/reversa_api/config.py` | 28 | Env-driven settings |
| 17 | `reversa/apps/api/src/reversa_api/routes/health.py` | 38 | `/health`, `/healthz`, `/readyz` — always HTTP 200 |
| 18 | `reversa/apps/api/src/reversa_api/__init__.py` | 3 | `__version__ = "0.1.0"` |
| 19 | `.gitignore` | 13 | Line 9 ignores `.env` |
| 20 | `README.md` | 96 | Live URL, architecture, no deploy/runbook section |
| 21 | `prompt.txt` | §250–284 (excerpt) | AGENT-11 deliverables: releases, migrations, rollback, fresh-install tests |

NOT read: `reversa/infrastructure/.env` (live secrets; verified untracked, left untouched).

## 4. Files modified

- `.agents/cycles/cycle-V2-01/agent-10-release-audit.md` (this file) — created.

## 5. Commands run (all read-only)

1. `Get-ChildItem` listings of repo root, `.github`, `.agents` — located CI + agent dirs.
2. `ripgrep ^` over deploy/docker/makefile globs — found only `reversa/apps/web/package.json`
   (first pass missed shell files due to glob wording; corrected by pass 3).
3. Case-insensitive regex search `deploy|rollback|backup|migrat|release|docker|alembic|prisma` —
   located `reversa/infrastructure/` (compose, scripts), `db.py`, `Dockerfile`s.
4. `Get-ChildItem reversa/infrastructure -Recurse`, `reversa/apps/web`, `reversa_api` —
   enumerated deploy surface. (`reversa/infrastructure/docker/` is empty.)
5. `git ls-files reversa/infrastructure` — tracked: compose, Caddyfile, `.env.example`,
   3 scripts. `.env` NOT tracked. `git check-ignore -v` confirms `.gitignore:9:.env`.
   `git log --oneline -5` — HEAD `6941d67`.
6. One over-broad `Get-ChildItem -Recurse` under `reversa/` (hit `.venv/`, ~1 MB listing)
   was terminated immediately via session terminate; no further broad scans.

No tests executed, no containers built, no deploy run, no SSH to the VM.

## 6. Observed results

### 6.1 CI gates (`ci.yml`, 27 lines)

- Triggers: `push` on `main` + all `pull_request`. Two independent jobs, no `needs`.
- `api` job: `pip install -e "reversa/apps/api[dev]"` then
  `python -m pytest reversa/apps/api/tests -q`.
- `web` job: `npm ci`, `npm run lint` (= `tsc --noEmit`), `npm run build`.
- Present and good: API unit tests gate every PR; web typecheck + build gate every PR.
- Absent: Python lint (ruff is configured in `pyproject.toml` but never run),
  Python typecheck, Docker image builds (both `Dockerfile`s are untested by CI),
  migration checks (moot — none exist, see §6.4), security/secret scan,
  fresh-install test, e2e/smoke, concurrency/cancel, action SHA pinning
  (`@v4`/`@v5` tags only — acceptable, mutable).

### 6.2 Deploy path

- `deploy.sh`: `cd` to infra dir, require `.env`, `docker compose up -d --build`,
  then `./scripts/healthcheck.sh`. Manual SSH procedure, no CD workflow.
- `docker-compose.yml`: pinned base images (`postgres:16-alpine`, `caddy:2-alpine`),
  own `api`/`web` images built from working tree with NO tag (implicit `:latest`).
  Healthchecks on postgres (pg_isready) and api (urllib fetch of `/healthz`).
  Volumes `pgdata/appdata/caddydata/caddyconfig` persist state.
- `healthcheck.sh`: curls `https://${DOMAIN}/healthz`, `/`, `/readyz` with `-fsS`.
- `web/Dockerfile` multi-stage standalone build matches `next.config.ts`
  (`output: "standalone"`); `npm ci || npm install` fallback weakens reproducibility.
- `api/Dockerfile`: single stage, runs as root, no `HEALTHCHECK` (compose covers it).

### 6.3 Rollback — DOES NOT EXIST

- No rollback script, no image tags to roll back to, no documented procedure.
- Rollback today = manual `git checkout <prev> && docker compose up -d --build`.
- No DB downgrade path exists (consequence of §6.4).
- Mitigating factor: evidence hash chain is append-only at app level, so a code
  rollback does not corrupt already-sealed evidence exports.

### 6.4 Backup — DOES NOT EXIST

- No backup script, cron, `pg_dump`, SQLite snapshot, or restore documentation found
  anywhere in the repo (search §5.3 + infra listing §5.4).
- State at risk on the single VM: `pgdata` (main store: workflows/actions/events),
  `appdata` (6 SQLite files), `.env` (exists only on the VM + dev machines).

### 6.5 Migration safety — NO MIGRATION SYSTEM

- Schema is created by `init_db()` (`db.py:56-65`): `Base.metadata.create_all`
  for `main` tables + `demo_resources` per demo store with `checkfirst=True`.
- `create_all` creates missing TABLES but never alters existing ones: any future
  column/index change silently does nothing on existing DBs (or requires manual SQL).
- No Alembic (prompt.txt line 733 mentions Alembic as an expectation; it was never
  added — `pyproject.toml` has no such dependency).
- Dual-engine risk: `main` is Postgres in prod but SQLite locally; demo stores are
  always SQLite. Any future migration must be tested on BOTH engines.
- `DateTime(timezone=True)` + naive-UTC convention (`models.py:14-26`) is handled
  in code; a migration touching datetime columns must preserve it.

## 7. Tests

None run. This is a static audit; per mandate no test or deployment results are
claimed. CI green status was not verified (no `gh` run, no push).

## 8. Issues (ordered by severity)

| ID | Severity | Finding | Evidence |
|----|----------|---------|----------|
| I-1 | High | No backup of any kind; single VM holds pgdata + appdata + .env | §6.4, compose vols L66-69 |
| I-2 | High | No rollback path (untagged images, no procedure, no DB downgrade) | §6.3, deploy.sh |
| I-3 | High | No migration system; `create_all` silently ignores schema changes on existing DBs | db.py:56-65 |
| I-4 | Medium | `deploy.sh` never sources `.env`, but `healthcheck.sh` requires `$DOMAIN` exported (`${DOMAIN:?...}`) → post-deploy verify fails unless the operator exported it manually | deploy.sh:6-8, healthcheck.sh:5 |
| I-5 | Medium | `/healthz` and `/readyz` return HTTP 200 even when DB is down (`status: degraded` in body only); `curl -fsS` and the compose healthcheck (urllib, no body check) both pass on degraded | health.py:24-33, compose L35 |
| I-6 | Medium | No readiness/liveness distinction: `/readyz` is byte-identical logic to `/healthz` | health.py:14-33 |
| I-7 | Low | CI never builds Docker images — broken `Dockerfile` merges green | ci.yml, both Dockerfiles |
| I-8 | Low | Ruff configured but never run in CI; no Python lint gate | pyproject L28-29, ci.yml |
| I-9 | Low | API has no lock file; `pip install` uses version ranges (reproducible-ish, not locked) | pyproject L6-13 |
| I-10 | Low | `web/Dockerfile` falls back `npm ci → npm install` (non-reproducible on lock drift) | web/Dockerfile L6 |
| I-11 | Low | API container runs as root | api/Dockerfile |
| I-12 | Info | Demo token printed to server log on first boot — fine for hackathon, remove/rotate for prod | main.py:31 |
| I-13 | Info | `reversa/infrastructure/docker/` is empty (dead directory or planned location) | §5.4 |

## 9. Risks

- R-1 (data loss): VM loss or bad deploy destroys prod data; nothing to restore from (I-1).
- R-2 (failed deploy undetected): degraded DB still reports healthy at every layer
  (I-5) — deploy.sh can print OK against a broken API.
- R-3 (schema drift): first V2 model change will half-apply (new tables yes, altered
  tables no) across Postgres/SQLite with no tooling to detect it (I-3).
- R-4 (operator error): manual SSH deploy + DOMAIN pitfall (I-4) + no runbook in README.
- R-5 (secret handling — currently GOOD): `.env` untracked + gitignored; the risk is
  future (a `--force` add or a debug CI step echoing env). Keep the `NEVER commit` rule.

## 10. Proposed release-candidate process (fits 1-VM reality, no new infra)

Principles: every prod deploy is preceded by a backup; every release is a tag that
can be rebuilt; verify with behavior, not just HTTP 200.

### 10.1 Versioning

- Single source of truth per app: `__version__` (API) + `version` (web `package.json`);
  bump together, tag `vX.Y.Z` on main. `0.1.0` → first RC is `v0.2.0-rc.1`.
- Health payloads already expose `version` (health.py:21) — use it to confirm WHAT
  is running after each deploy.

### 10.2 RC checklist (run top to bottom, stop on first red)

1. **Cut RC**: `git tag vX.Y.Z-rc.N && git push origin vX.Y.Z-rc.N` from green main.
2. **CI green** on the tag: pytest + tsc + web build (today's gates).
3. **Image build gate**: `docker build` api + web from the tag (add to CI when able;
   until then, build once on the VM with `-t reversa-api:vX.Y.Z-rc.N` — never `:latest`
   alone — and keep the previous tag).
4. **Fresh-install test** (covers AGENT-11 deliverable): on a throwaway dir/VM,
   `cp .env.example .env`, fill dummy values, `docker compose up -d --build`,
   run healthcheck + create one workflow via API. Destroys nothing in prod.
5. **Backup prod** (new `scripts/backup.sh`): timestamp dir; `pg_dump` from the
   postgres container; `tar.gz` of the 6 SQLite files from the api container
   (`/data/*.db`); record `git rev-parse HEAD` + image tags + `docker compose config`
   into the backup dir. Verify non-empty before proceeding.
6. **Deploy**: `git fetch && git checkout vX.Y.Z-rc.N` on the VM,
   `docker compose up -d --build`, then fixed `healthcheck.sh` (I-4).
7. **Behavioral verify** (beyond `/healthz`): `GET /readyz` shows expected `version`
   and `"db": true`; `POST` one demo workflow end-to-end; export evidence and run
   `python -m reversa_api.cli verify`. Any red → §10.3.
8. **Promote**: retag `vX.Y.Z-rc.N` → `vX.Y.Z`, note backup location + image tags
   in the release notes.

### 10.3 Rollback (until real tags exist, document this manual path)

1. `git checkout <previous-release-tag>` on the VM.
2. `docker compose up -d --build` (rebuilds previous code; keep a copy of the
   previous `docker compose config` from the backup dir for reference).
3. Re-run §10.2 step 7 against the previous version.
4. DB: restore from §10.2 step 5 ONLY if the failed release changed the schema
   (no-op today — there are no migrations; mandatory once Alembic lands).
5. Never delete the previous working images until the new release is promoted.

### 10.4 Migration policy (V2)

- If V2 changes NO model: keep `create_all`, document "no migration in this release".
- If V2 changes ANY model: adopt Alembic THEN (not before — no speculative tooling):
  autogenerate, hand-review, test `upgrade` + `downgrade` against SQLite AND Postgres
  (dockerized `postgres:16-alpine`), run upgrade inside backup/restore window of §10.2.
- Never edit prod schema by hand without recording the SQL in the release notes.

### 10.5 Suggested backlog (not implemented — audit mandate is read-only)

1. `scripts/backup.sh` + `docs/runbook.md` (deploy/rollback/restore) — kills R-1/R-4.
2. Fix I-4: `set -a; . ./.env; set +a` in `deploy.sh` (or read DOMAIN in healthcheck).
3. Fix I-5/I-6: `/healthz` → 200 always (liveness); `/readyz` → 503 when `db` is false
   (readiness); make compose api healthcheck hit `/readyz`.
4. CI: add `docker build` for api+web, `ruff check`, keep-first `pip` cache.
5. Tag images per release; `swap `:latest`-only deploys for pinned tags.
6. Alembic on first schema change (see §10.4), dual-engine tested.

## 11. Confidence

- High: CI gaps, deploy-script contents, missing backup/rollback/migration (every
  cited file read in full; absence verified by repo-wide search + directory listing).
- Medium: operational state of the live VM (not accessed; `.env` deliberately unread;
  actual prod data volume and deploy history unknown).
- Not assessed: GitHub Actions runner history, VM OS/hardening, Vultr snapshot config.

## 12. Next task (recommended for the implementer)

Implement backlog items 1–3 (§10.5): `backup.sh` + runbook, DOMAIN fix, health/ready
semantics. Smallest increment that converts "deploy and hope" into "backup, deploy,
verify, roll back". Alembic only when the first V2 model change is specified.
