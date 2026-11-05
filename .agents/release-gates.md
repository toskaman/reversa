# REVERSA Release Gates (RC Checklist)

Durable RC checklist. Every prod deploy cuts an RC that passes ALL gates top to
bottom. Stop on first red. Per-cycle evidence lives in
`.agents/cycles/cycle-<X>/agent-10-rc-plan.md`.

## G1 — Tests green

- API suite passes with zero failures on the RC commit.
- No new skips without a recorded reason.

## G2 — Build green

- Web typecheck (`lint`) and production build pass on the RC commit.
- Both Docker images (`api`, `web`) build from the RC tree.

## G3 — Secrets scan clean

- No secrets committed: `.env` untracked + gitignored, no key/token/password
  literals in tracked files, no CI step echoing env.
- Scan run on the RC diff and clean.

## G4 — Migrations safe

- If the RC changes NO model: declare "no migration in this release".
- If the RC changes ANY model: Alembic upgrade + downgrade tested on SQLite
  AND Postgres before deploy; upgrade runs inside the backup window.

## G5 — Rollback ready

- Previous release tag + image tags + `docker compose config` recorded.
- Prod backup (pg_dump + SQLite tarball) fresh and verified non-empty.
- Rollback procedure rehearsed or previously executed.

## G6 — Version pin

- `__version__` (API) and `version` (web `package.json`) bumped together.
- RC tagged `vX.Y.Z-rc.N`; `:latest`-only deploys forbidden — images tagged
  per release; previous tag kept until promotion.
- Post-deploy `/readyz` reports the expected version.

## Promotion

Retag `vX.Y.Z-rc.N` → `vX.Y.Z`; record backup location + image tags in the
release notes. Never delete previous working images before promotion.
