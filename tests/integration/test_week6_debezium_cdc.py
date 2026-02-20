import asyncio
import json
import os
import sys
import time
import uuid
from typing import Any

import httpx
import pytest
from aiokafka import AIOKafkaConsumer

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))


def _in_compose_network() -> bool:
    return os.getenv("MYSQL_HOST", "").strip() == "mysql"


def _debezium_url() -> str:
    v = os.getenv("DEBEZIUM_CONNECT_URL", "").strip()
    if v:
        return v
    return "http://debezium:8083" if _in_compose_network() else "http://localhost:8083"


def _kafka_bootstrap() -> str:
    v = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "").strip()
    if v:
        return v
    return "kafka:9092" if _in_compose_network() else "localhost:29092"


def _mysql_conn_config() -> dict[str, Any]:
    from riskmonitor_multiagent import config

    return {
        "database": config.get_mysql_database(),
        "user": config.get_mysql_user(),
        "password": config.get_mysql_password(),
    }


def _wait_http_ok(url: str, *, path: str, timeout_s: float = 30.0) -> None:
    started = time.monotonic()
    while time.monotonic() - started < timeout_s:
        try:
            r = httpx.get(url.rstrip("/") + path, timeout=2.0)
            if 200 <= r.status_code < 300:
                return
        except Exception:
            pass
        time.sleep(0.5)
    raise RuntimeError(f"http_not_ready:{url}{path}")


def _ensure_positions_connector() -> tuple[str, str]:
    url = _debezium_url()
    _wait_http_ok(url, path="/connectors")

    suffix = uuid.uuid4().hex[:8]
    name = f"risk-positions-connector-it-{suffix}"
    topic = f"risk.positions.cdc.it.{suffix}"
    cfg = json.loads(open("scripts/debezium/positions-connector.json", "r", encoding="utf-8").read())
    cfg = dict(cfg) if isinstance(cfg, dict) else {}
    cfg_name = name
    config_obj = cfg.get("config") if isinstance(cfg.get("config"), dict) else {}
    mysql_cfg = _mysql_conn_config()
    config_obj = dict(config_obj)
    config_obj["database.hostname"] = "mysql"
    config_obj["database.port"] = "3306"
    config_obj["database.user"] = mysql_cfg["user"]
    config_obj["database.password"] = mysql_cfg["password"]
    config_obj["database.include.list"] = mysql_cfg["database"]
    config_obj["table.include.list"] = f"{mysql_cfg['database']}.positions"
    config_obj["schema.history.internal.kafka.topic"] = f"risk.schema_history.it.{suffix}"
    config_obj["transforms.route.replacement"] = topic
    config_obj["snapshot.mode"] = "schema_only"
    payload = {"name": cfg_name, "config": config_obj}

    r = httpx.get(url.rstrip("/") + "/connectors", timeout=5.0)
    r.raise_for_status()
    existing = r.json()
    if isinstance(existing, list) and cfg_name in existing:
        r2 = httpx.put(url.rstrip("/") + f"/connectors/{cfg_name}/config", json=config_obj, timeout=10.0)
        r2.raise_for_status()
    else:
        r2 = httpx.post(url.rstrip("/") + "/connectors", json=payload, timeout=10.0)
        r2.raise_for_status()

    started = time.monotonic()
    while time.monotonic() - started < 120.0:
        try:
            st = httpx.get(url.rstrip("/") + f"/connectors/{cfg_name}/status", timeout=5.0)
            if 200 <= st.status_code < 300:
                data = st.json()
                conn = data.get("connector") if isinstance(data, dict) else None
                state = conn.get("state") if isinstance(conn, dict) else None
                tasks = data.get("tasks") if isinstance(data, dict) else None
                task_states = [t.get("state") for t in tasks] if isinstance(tasks, list) else []
                if state == "RUNNING" and task_states and all(s == "RUNNING" for s in task_states):
                    return cfg_name, topic
        except Exception:
            pass
        time.sleep(1.0)
    raise RuntimeError("debezium_connector_not_running")


def _insert_position(*, position_id: str, trader_id: str, desk: str, delta: float) -> None:
    from riskmonitor_multiagent.data_access.mysql_engine import get_engine

    conn = get_engine().raw_connection()
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO positions (position_id, trader_id, desk, security_id, quantity, delta, entry_date, currency)
            VALUES (%s, %s, %s, %s, %s, %s, CURDATE(), %s)
            """,
            (position_id, trader_id, desk, "SEC_TEST", 1.0, float(delta), "USD"),
        )
        conn.commit()
    finally:
        try:
            if cursor is not None:
                cursor.close()
        finally:
            conn.close()


@pytest.mark.asyncio
async def test_week6_debezium_mysql_to_kafka_cdc_end_to_end():
    try:
        connector, topic = _ensure_positions_connector()
        assert isinstance(connector, str) and connector
        assert isinstance(topic, str) and topic
    except Exception as e:
        pytest.skip(f"requires docker middleware (debezium/kafka/mysql): {e}")

    bootstrap = _kafka_bootstrap()

    group_id = f"rm-it-{uuid.uuid4().hex}"
    consumer = AIOKafkaConsumer(
        topic,
        bootstrap_servers=bootstrap,
        group_id=group_id,
        auto_offset_reset="latest",
        enable_auto_commit=True,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
    )
    try:
        await consumer.start()
    except Exception as e:
        pytest.skip(f"requires docker kafka: {e}")
    try:
        position_id = f"it-{uuid.uuid4().hex[:10]}"
        _insert_position(position_id=position_id, trader_id="TRADER_IT", desk="IT Desk", delta=123.45)

        deadline = time.monotonic() + 45.0
        while time.monotonic() < deadline:
            batch = await consumer.getmany(timeout_ms=1500, max_records=50)
            for _, msgs in batch.items():
                for m in msgs:
                    val = m.value if isinstance(m.value, dict) else None
                    if not isinstance(val, dict):
                        continue
                    payload = val.get("payload")
                    if isinstance(val.get("after"), dict):
                        rec = val.get("after") or {}
                    elif isinstance(payload, dict) and isinstance(payload.get("after"), dict):
                        rec = payload.get("after") or {}
                    elif isinstance(payload, dict):
                        rec = payload
                    else:
                        rec = val
                    if isinstance(rec, dict) and str(rec.get("position_id") or "") == position_id:
                        return
        raise AssertionError("cdc_message_not_observed")
    finally:
        await consumer.stop()
