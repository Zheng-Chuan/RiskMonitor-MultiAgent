#!/usr/bin/env bash
set -euo pipefail

CONNECT_URL="${CONNECT_URL:-http://localhost:8083}"
CONNECTOR_FILE="${CONNECTOR_FILE:-scripts/debezium/positions-connector.json}"

echo "Waiting Debezium Connect: ${CONNECT_URL} ..."
for i in $(seq 1 60); do
  if curl -fsS "${CONNECT_URL}/connectors" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! curl -fsS "${CONNECT_URL}/connectors" >/dev/null 2>&1; then
  echo "Debezium Connect not ready: ${CONNECT_URL}"
  exit 1
fi

echo "Register connector from ${CONNECTOR_FILE}"
payload="$(cat "${CONNECTOR_FILE}")"
name="$(python - <<'PY'
import json,sys
print(json.loads(sys.stdin.read())["name"])
PY
<<<"${payload}")"

if curl -fsS "${CONNECT_URL}/connectors/${name}" >/dev/null 2>&1; then
  echo "Connector exists, updating: ${name}"
  config="$(python - <<'PY'
import json,sys
obj=json.loads(sys.stdin.read())
print(json.dumps(obj["config"]))
PY
<<<"${payload}")"
  curl -fsS -X PUT "${CONNECT_URL}/connectors/${name}/config" \
    -H "Content-Type: application/json" \
    -d "${config}" >/dev/null
  echo "Updated: ${name}"
  exit 0
fi

curl -fsS -X POST "${CONNECT_URL}/connectors" \
  -H "Content-Type: application/json" \
  -d "${payload}" >/dev/null

echo "Created: ${name}"

