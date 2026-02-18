import json
import time
import uuid

import httpx


def _wait_registry(url: str, timeout_s: float = 20.0) -> None:
    started = time.monotonic()
    while time.monotonic() - started < timeout_s:
        try:
            r = httpx.get(url.rstrip("/") + "/subjects", timeout=2.0)
            if 200 <= r.status_code < 300:
                return
        except Exception:
            pass
        time.sleep(0.5)
    raise RuntimeError("schema_registry_not_ready")


def _register_json_schema(*, url: str, subject: str, schema_obj: dict) -> None:
    payload = {"schemaType": "JSON", "schema": json.dumps(schema_obj, ensure_ascii=False, sort_keys=True)}
    r = httpx.post(
        url.rstrip("/") + f"/subjects/{subject}/versions",
        json=payload,
        headers={"Content-Type": "application/vnd.schemaregistry.v1+json"},
        timeout=5.0,
    )
    r.raise_for_status()


def _set_compatibility(*, url: str, subject: str, level: str) -> None:
    r = httpx.put(
        url.rstrip("/") + f"/config/{subject}",
        json={"compatibility": level},
        timeout=5.0,
    )
    r.raise_for_status()


def _check_compat(*, url: str, subject: str, schema_obj: dict) -> bool:
    payload = {"schemaType": "JSON", "schema": json.dumps(schema_obj, ensure_ascii=False, sort_keys=True)}
    r = httpx.post(url.rstrip("/") + f"/compatibility/subjects/{subject}/versions/latest", json=payload, timeout=5.0)
    r.raise_for_status()
    data = r.json()
    return bool(isinstance(data, dict) and data.get("is_compatible") is True)


def test_week16_schema_registry_json_schema_compatibility():
    url = "http://localhost:8085"
    _wait_registry(url)
    subject = f"riskmonitor-test-{uuid.uuid4().hex}-value"

    base_schema = json.loads(
        open("schemas/cdc/positions_cdc_v1.schema.json", "r", encoding="utf-8").read()
    )
    _register_json_schema(url=url, subject=subject, schema_obj=base_schema)
    _set_compatibility(url=url, subject=subject, level="BACKWARD")

    compatible = dict(base_schema)
    compatible["title"] = str(base_schema.get("title") or "") + " (metadata only)"
    assert _check_compat(url=url, subject=subject, schema_obj=compatible) is True

    breaking_add_field = dict(base_schema)
    breaking_add_field["properties"] = dict(base_schema.get("properties") or {})
    breaking_add_field["properties"]["book"] = {"type": ["string", "null"]}
    assert _check_compat(url=url, subject=subject, schema_obj=breaking_add_field) is False
