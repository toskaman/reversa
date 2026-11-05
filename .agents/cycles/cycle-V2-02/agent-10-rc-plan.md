# AGENT-10 — RC Plan, REVERSA V2 cycle 2 (Release Engineer)

Maps each gate in `.agents/release-gates.md` to its verification command.
Base: HEAD `63bb949` (V2-01 merged), clean tree, no tags. Versions `0.1.0`
(API `__version__` + web `package.json`); first RC is `v0.2.0-rc.1`.

## Gate → command map

| Gate | Verification command(s) | Pass criterion |
|------|-------------------------|----------------|
| G1 tests | `reversa/apps/api/.venv/Scripts/python.exe -m pytest reversa/apps/api/tests -q` (repo root; CI equivalent: `python -m pytest reversa/apps/api/tests -q` per `ci.yml:15`) | `49 passed, 2 skipped` observed 2026-11-05 on clean base; RC must show 0 failed, no new skips |
| G2 build/web | `npm run --prefix reversa/apps/web lint` then `npm run --prefix reversa/apps/web build` (per `ci.yml:25-27`) | Both exit 0 |
| G2 build/images | `docker build -f reversa/apps/api/Dockerfile -t reversa-api:vX.Y.Z-rc.N reversa/apps/api` and `docker build -f reversa/apps/web/Dockerfile -t reversa-web:vX.Y.Z-rc.N reversa/apps/web` | Both exit 0; never `:latest` alone |
| G3 secrets | `git status --short` (expect empty) + `git check-ignore -v reversa/infrastructure/.env` (expect `.gitignore:9:.env`) + `git ls-files \| grep -iE '\.env$'` (expect no output) + grep RC diff for `(?i)api[_-]?key\|secret\|token\s*=\s*['\"][^'\"]+['\"]\|password` excluding redaction/test fixtures | All clean; `.env` untracked |
| G4 migrations | `git diff <prev-tag>..<rc-tag> -- reversa/apps/api/src/reversa_api/models.py reversa/apps/api/src/reversa_api/db.py` | Empty → declare "no migration in this release" (schema = `create_all`, `db.py:56-65`). Non-empty → Alembic upgrade+downgrade on SQLite AND `postgres:16-alpine` required before deploy |
| G5 rollback | Record `git rev-parse HEAD`, image tags, `docker compose config` (in `reversa/infrastructure/`); prod backup per V2-01 §10.2 step 5 (pg_dump + `/data/*.db` tarball); verify non-empty with `ls -la <backup-dir>` | Backup dir non-empty; previous tag documented; rollback = V2-01 §10.3 |
| G6 version pin | `grep -r __version__ reversa/apps/api/src/reversa_api/__init__.py` + `grep '"version"' reversa/apps/web/package.json` must agree; `git tag vX.Y.Z-rc.N` from green main | Versions match; tag exists; post-deploy `curl -fsS "https://${DOMAIN}/readyz"` shows expected `version` and `"db": true` |

## RC run order (stop on first red)

1. `git status --short` → empty; `git log --oneline -1` → RC commit.
2. G1, G2 (lint+build, then images), G3, G4 (declare or migrate).
3. Fresh-install test (throwaway dir): `cp .env.example .env`, dummy values,
   `docker compose up -d --build`, healthcheck + one workflow via API.
4. G5 backup prod, then deploy on VM: `git fetch && git checkout vX.Y.Z-rc.N`,
   `docker compose up -d --build`, `./scripts/healthcheck.sh`
   (export `DOMAIN` first — V2-01 I-4 pitfall).
5. Behavioral verify: `/readyz` version + `db:true`, one demo workflow
   end-to-end, evidence export + `python -m reversa_api.cli verify`.
6. Promote: retag `vX.Y.Z`; note backup + tags in release notes.

## Known gaps inherited from V2-01 audit (not re-verified)

- No `backup.sh`, no rollback script, no Alembic, CI builds no images,
  ruff never run, `/readyz` ≡ `/healthz` (always 200), `deploy.sh` doesn't
  export `DOMAIN`. See `cycle-V2-01/agent-10-release-audit.md` §8–§10.
