#!/bin/sh
# REVERSA deploy: build + start + verify. Idempotent. Run on the VM in
# reversa/infrastructure with .env present.
set -eu
cd "$(dirname "$0")/.."
test -f .env || { echo "missing .env (see .env.example)"; exit 1; }
# Export .env so DOMAIN/POSTGRES_PASSWORD reach compose AND healthcheck.sh
# (compose reads .env itself; the child script needs it exported).
set -a
# shellcheck disable=SC1091
. ./.env
set +a
: "${DOMAIN:?set DOMAIN in .env}"
: "${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD in .env}"
docker compose up -d --build
./scripts/healthcheck.sh
