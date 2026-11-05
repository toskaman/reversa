#!/bin/sh
# External-style health verification against the public domain.
set -eu
cd "$(dirname "$0")/.."
DOMAIN="${DOMAIN:?set DOMAIN}"
echo "== api =="
curl -fsS "https://${DOMAIN}/healthz"
echo
echo "== web =="
curl -fsS -o /dev/null -w "web %{http_code}\n" "https://${DOMAIN}/"
echo "== ready =="
curl -fsS "https://${DOMAIN}/readyz"
echo
echo OK
