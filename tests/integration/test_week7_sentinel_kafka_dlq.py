import asyncio
import json
import os
import sys
import time
import uuid

import pytest
from aiokafka import AIOKafkaConsumer

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))


def _in_compose_network() -> bool:
    return os.getenv("MYSQL_HOST", "").strip() == "mysql"


def _kafka_bootstrap() -> str:
    v = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "").strip()
    if v:
        return v
    return "kafka:9092" if _in_compose_network() else "localhost:29092"


class _Msg:
    def __init__(self, value, *, topic: str, partition: int, offset: int, timestamp: int):
        self.value = value
        self.topic = topic
        self.partition = partition
        self.offset = offset
        self.timestamp = timestamp


@pytest.mark.asyncio
async def test_week7_sentinel_publishes_dlq_to_kafka_when_processing_fails(monkeypatch):
    from riskmonitor_multiagent.sentinel.service import MAX_EXPOSURE_THRESHOLD, SentinelService

    bootstrap = _kafka_bootstrap()
    dlq_topic = f"risk.dlq.it.{uuid.uuid4().hex[:8]}"
    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", bootstrap)
    monkeypatch.setenv("KAFKA_TOPIC_DLQ", dlq_topic)
    monkeypatch.setenv("SENTINEL_DLQ_ENABLED", "1")
    monkeypatch.setenv("SENTINEL_RETRY_MAX", "2")
    monkeypatch.setenv("SENTINEL_RETRY_BACKOFF_S", "0")

    consumer = AIOKafkaConsumer(
        dlq_topic,
        bootstrap_servers=bootstrap,
        group_id=f"rm-dlq-it-{uuid.uuid4().hex}",
        auto_offset_reset="earliest",
        enable_auto_commit=True,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
    )
    try:
        await consumer.start()
    except Exception as e:
        pytest.skip(f"requires docker kafka: {e}")
    try:
        svc = SentinelService()

        async def _boom(*, event: dict):
            raise RuntimeError("boom")

        svc._trigger_alert = _boom  # type: ignore[attr-defined]

        now_ms = int(time.time() * 1000)
        offset = int(now_ms)
        msg = _Msg(
            {
                "payload": {
                    "op": "u",
                    "after": {"desk": "Equity Derivatives", "delta": float(MAX_EXPOSURE_THRESHOLD) + 10.0},
                }
            },
            topic="risk.positions.cdc",
            partition=0,
            offset=offset,
            timestamp=now_ms,
        )

        await svc._process_message(msg)

        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            batch = await consumer.getmany(timeout_ms=1000, max_records=10)
            for _, msgs in batch.items():
                for m in msgs:
                    val = m.value if isinstance(m.value, dict) else None
                    if not isinstance(val, dict):
                        continue
                    if val.get("schema_version") != "dlq_event.v1":
                        continue
                    if val.get("topic") == "risk.positions.cdc" and int(val.get("offset") or -1) == offset:
                        assert val.get("attempts") == 2
                        err = val.get("error")
                        assert isinstance(err, dict) and err.get("code") in {"RuntimeError", "Exception"}
                        return
        raise AssertionError("dlq_message_not_observed")
    finally:
        await consumer.stop()
