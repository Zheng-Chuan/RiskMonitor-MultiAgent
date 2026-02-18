import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))


def _unique_offset() -> int:
    import time

    return int(time.time() * 1000)


def test_week16_processed_cdc_events_idempotency_roundtrip():
    from riskmonitor_multiagent.data_access import idempotency_repository

    topic = "risk.positions.cdc"
    partition = 0
    offset = _unique_offset()
    event_id = f"{topic}:{partition}:{offset}"

    d1 = idempotency_repository.try_begin_processing(topic=topic, partition=partition, offset=offset, event_id=event_id)
    assert d1.decision == "process"
    assert d1.attempts == 1

    idempotency_repository.mark_done(topic=topic, partition=partition, offset=offset)

    d2 = idempotency_repository.try_begin_processing(topic=topic, partition=partition, offset=offset, event_id=event_id)
    assert d2.decision == "skip_done"


def test_week16_processed_cdc_events_failed_can_retry():
    from riskmonitor_multiagent.data_access import idempotency_repository

    topic = "risk.positions.cdc"
    partition = 0
    offset = _unique_offset() + 1
    event_id = f"{topic}:{partition}:{offset}"

    d1 = idempotency_repository.try_begin_processing(topic=topic, partition=partition, offset=offset, event_id=event_id)
    assert d1.decision == "process"
    assert d1.attempts == 1

    idempotency_repository.mark_failed(topic=topic, partition=partition, offset=offset, error_message="boom")
    status = idempotency_repository.get_status(topic=topic, partition=partition, offset=offset)
    assert isinstance(status, dict)
    assert status.get("status") == "failed"

    d2 = idempotency_repository.try_begin_processing(topic=topic, partition=partition, offset=offset, event_id=event_id)
    assert d2.decision == "process"
    assert d2.attempts >= 2

