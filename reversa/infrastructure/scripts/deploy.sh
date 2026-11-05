#!/bin/sh
# REVERSA deploy: build + start + verify. Idempotent. Run on the VM in
# reversa/infrastructure with .env present.
set -eu
cd "$(dirname "$0")/.."
test -f .env || { echo "missing .env (see .env.example)"; exit 1; }
docker compose up -d --build
./scripts/healthcheck.sh
