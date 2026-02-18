from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx


def _load_schema_file(path: str) -> str:
    obj = json.loads(Path(path).read_text(encoding="utf-8"))
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def check_compatibility(*, registry_url: str, subject: str, schema_file: str, version: str = "latest") -> dict:
    schema_json = _load_schema_file(schema_file)
    payload = {"schemaType": "JSON", "schema": schema_json}
    url = registry_url.rstrip("/") + f"/compatibility/subjects/{subject}/versions/{version}"
    resp = httpx.post(url, json=payload, timeout=10.0)
    return {"status_code": int(resp.status_code), "body": resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--registry-url", default="http://localhost:8085")
    p.add_argument("--subject", default="risk.positions.cdc-value")
    p.add_argument("--schema-file", default="schemas/cdc/positions_cdc_v1.schema.json")
    p.add_argument("--version", default="latest")
    args = p.parse_args()

    out = check_compatibility(
        registry_url=str(args.registry_url),
        subject=str(args.subject),
        schema_file=str(args.schema_file),
        version=str(args.version),
    )
    print(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True))
    body = out.get("body")
    is_compat = isinstance(body, dict) and body.get("is_compatible") is True
    return 0 if is_compat else 1


if __name__ == "__main__":
    raise SystemExit(main())

