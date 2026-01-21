#!/usr/bin/env bash
set -euo pipefail

SCHEMA_REGISTRY_URL="${SCHEMA_REGISTRY_URL:-http://localhost:8085}"
SCHEMA_FILE="${SCHEMA_FILE:-schemas/cdc/positions_cdc_v1.schema.json}"
SUBJECT="${SUBJECT:-risk.positions.cdc-value}"

echo "Waiting Schema Registry: ${SCHEMA_REGISTRY_URL} ..."
for i in $(seq 1 60); do
  if curl -fsS "${SCHEMA_REGISTRY_URL}/subjects" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! curl -fsS "${SCHEMA_REGISTRY_URL}/subjects" >/dev/null 2>&1; then
  echo "Schema Registry not ready: ${SCHEMA_REGISTRY_URL}"
  exit 1
fi

schema_json="$(python - <<'PY'
import json,sys
obj=json.load(open(sys.argv[1], "r", encoding="utf-8"))
print(json.dumps(obj, ensure_ascii=False))
PY
"${SCHEMA_FILE}")"

payload="$(python - <<'PY'
import json,sys
schema=sys.stdin.read()
print(json.dumps({"schemaType":"JSON","schema":schema}))
PY
<<<"${schema_json}")"

curl -fsS -X POST "${SCHEMA_REGISTRY_URL}/subjects/${SUBJECT}/versions" \
  -H "Content-Type: application/vnd.schemaregistry.v1+json" \
  -d "${payload}" >/dev/null

echo "Registered JSON schema subject=${SUBJECT} from ${SCHEMA_FILE}"

