#!/bin/sh
# Run inside a clean distro container after installing the package.
# Starts the proxy as the service user and expects HTTP 401 without a token.
set -eu

set -a
. /etc/powerdns-api-proxy/powerdns-api-proxy.env
set +a

runuser -u powerdns-api-proxy -- /opt/powerdns-api-proxy/venv/bin/python -m powerdns_api_proxy &
PID=$!
trap 'kill $PID 2>/dev/null || true' EXIT

for _ in $(seq 1 30); do
    code="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${LISTEN_PORT}/api/v1/servers" || true)"
    [ "$code" = "401" ] && { echo "smoke test ok (HTTP $code)"; exit 0; }
    sleep 1
done
echo "smoke test failed (last HTTP code: ${code:-none})" >&2
exit 1
