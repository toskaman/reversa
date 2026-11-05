#!/bin/sh
# External-style health verification against the public domain.
set -eu
cd "$(dirname "$0")/.."
# Fall back to .env so direct runs work without an exported DOMAIN.
if [ -z "${DOMAIN:-}" ] && [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi
DOMAIN="${DOMAIN:?set DOMAIN (export it or define it in .env)}"
echo "== api =="
curl -fsS "https://${DOMAIN}/healthz"
echo
echo "== web =="
curl -fsS -o /dev/null -w "web %{http_code}\n" "https://${DOMAIN}/"
echo "== ready =="
curl -fsS "https://${DOMAIN}/readyz"
echo
echo OK
