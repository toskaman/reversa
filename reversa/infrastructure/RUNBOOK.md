# REVERSA Ops Runbook (1 VM: Caddy + API + Web + Postgres)

All commands run on the VM in `reversa/infrastructure/` with `.env` present
(copy `.env.example`, never commit `.env`).

## Deploy

```sh
./scripts/deploy.sh
```

Idempotent: builds + starts the stack, then verifies the public endpoints.
Fails fast when `DOMAIN` or `POSTGRES_PASSWORD` is missing from `.env`.

## Verify

```sh
./scripts/healthcheck.sh          # public https://$DOMAIN checks
curl -s https://$DOMAIN/healthz   # 200 {"status":"ok",...} when healthy
curl -s -o /dev/null -w "%{http_code}\n" https://$DOMAIN/readyz
```

Health contract (see `reversa/apps/api/tests/test_health.py`):

| Endpoint | DB up | DB down |
|---|---|---|
| `/health`, `/healthz`, `/api/v1/health` | 200 `{"status":"ok","db":true}` | **503** `{"status":"degraded","db":false}` |
| `/readyz` | 200 `{"ready":true,...}` | **503** `{"ready":false,...}` |

`/readyz` is the readiness gate: while it returns 503 the instance must be
treated as out of rotation. The compose `healthcheck` probes `/healthz`, so
a DB outage also marks the `api` container `unhealthy`
(`docker compose ps`).

## Backup

```sh
./scripts/backup.sh               # -> backups/reversa-<ts>-{postgres.sql.gz,appdata.tgz}
BACKUP_KEEP_DAYS=30 ./scripts/backup.sh   # custom retention (default 14d)
```

Nightly cron suggestion: `0 3 * * * cd /opt/reversa/reversa/infrastructure && ./scripts/backup.sh >> /var/log/reversa-backup.log 2>&1`.
Copy `backups/` off-VM (scp/rsync/S3) — a backup that lives only on the VM
is not a backup.

## Restore

Postgres (stops writers first):

```sh
docker compose stop api
gunzip -c backups/reversa-<ts>-postgres.sql.gz \
  | docker compose exec -T postgres psql -U reversa reversa
docker compose start api
./scripts/healthcheck.sh
```

App data (`/data` volume, demo sqlite files + uploads):

```sh
docker compose stop api
cat backups/reversa-<ts>-appdata.tgz \
  | docker compose run --rm --no-deps -T --entrypoint tar api -xzf - -C /
docker compose start api
```

(This reuses the `api` service definition, so the `appdata` volume mount
is exactly the one the app uses — no volume-name guessing.)

## Rotate secrets

1. New value in `.env` (`POSTGRES_PASSWORD=...`).
2. Postgres password: `docker compose exec postgres psql -U reversa -c "ALTER USER reversa PASSWORD '<new>';"`.
3. `docker compose up -d` (recreates `api` with the new `DATABASE_URL`).
4. `./scripts/healthcheck.sh`.

API tokens are per-org hashes in the DB (`scripts/add_token.py`), not env.

## Failure modes

| Symptom | Likely cause | Action |
|---|---|---|
| `/readyz` 503, `/healthz` 503 | Postgres down / wrong password | `docker compose logs postgres`, check `POSTGRES_PASSWORD`, restart `postgres` |
| `/readyz` 503 only at boot | API started before postgres healthy | Wait; `depends_on` + pg `healthcheck` should self-heal, else `docker compose restart api` |
| TLS errors on `$DOMAIN` | Caddy ACME rate-limit / DNS | Check `docker compose logs caddy`, DNS `A` record for `$DOMAIN` |
| `healthcheck.sh`: `DOMAIN ... .env` | No `.env` / no `DOMAIN` | Copy `.env.example` to `.env`, set `DOMAIN=<vm-ip>.nip.io` |
| Disk full | Old backups / pgdata growth | Prune `backups/`, `docker system df`, `docker system prune` |

## Rollback

Code rollback (config + images stay on the VM; `.env` is untouched):

```sh
git log --oneline -5                  # pick the last known-good sha
./scripts/backup.sh                   # safety snapshot BEFORE touching code
git checkout <previous-sha> -- reversa/apps reversa/infrastructure
docker compose up -d --build
./scripts/healthcheck.sh              # must end OK: /healthz 200, / 200, /readyz 200
```

Notes:

- The `git checkout <sha> -- <paths>` form updates the working tree + index
  but not HEAD. To return to the tip afterwards:
  `git checkout HEAD -- reversa/apps reversa/infrastructure`
  (or `git reset --hard HEAD` when no other local changes must be kept),
  then `docker compose up -d --build` + `./scripts/healthcheck.sh` again.
- Schema is `create_all(checkfirst=True)` (`db.py:init_db`) — there are no
  down-migrations to run, so a code rollback needs no schema downgrade.
- If the bad deploy wrote bad data (not just bad code), restore the
  pre-rollback backup from the step above (see Restore) after the code
  rollback; code-only rollback does not undo data writes.
- Prefer roll-forward (fix at HEAD, redeploy via `./scripts/deploy.sh`)
  when the fix is small; use rollback when prod is red and the fix is
  not immediate.
