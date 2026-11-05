#!/bin/sh
# REVERSA backup: postgres dump + /data snapshot. Run on the VM in
# reversa/infrastructure. Output: ./backups/ (git-ignored).
# Retention: BACKUP_KEEP_DAYS (default 14). Restore: see RUNBOOK.md.
set -eu
cd "$(dirname "$0")/.."
test -f .env || { echo "missing .env (see .env.example)"; exit 1; }
set -a
# shellcheck disable=SC1091
. ./.env
set +a

KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
TS="$(date -u +%Y-%m-%dT%H-%M-%SZ)"
OUT="backups/reversa-${TS}"
mkdir -p backups

echo "== postgres =="
docker compose exec -T postgres pg_dump -U reversa reversa \
  | gzip > "${OUT}-postgres.sql.gz"
echo "wrote ${OUT}-postgres.sql.gz"

echo "== appdata (/data) =="
if [ -n "$(docker compose ps -q api 2>/dev/null)" ]; then
  docker compose exec -T api tar -czf - -C / data > "${OUT}-appdata.tgz"
  echo "wrote ${OUT}-appdata.tgz"
else
  echo "api container not present, skipping /data snapshot"
fi

echo "== retention (keep ${KEEP_DAYS}d) =="
find backups -maxdepth 1 \
  \( -name 'reversa-*-postgres.sql.gz' -o -name 'reversa-*-appdata.tgz' \) \
  -mtime "+${KEEP_DAYS}" -print -delete
echo "== done =="
ls -la backups
