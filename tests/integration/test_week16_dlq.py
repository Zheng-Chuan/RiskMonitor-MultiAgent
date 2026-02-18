import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))


def _unique_offset() -> int:
    import time

    return int(time.time() * 1000)


def test_week16_dlq_events_persist_and_read_back():
    from riskmonitor_multiagent.data_access import dlq_repository

    topic = "risk.positions.cdc"
    partition = 0
    offset = _unique_offset()
    event_id = f"{topic}:{partition}:{offset}"

    dlq_repository.save_dlq_event(
        topic=topic,
        partition=partition,
        offset=offset,
        event_id=event_id,
        error_code="TEST",
        error_message="boom",
        payload={"k": "v"},
        attempts=3,
    )
    row = dlq_repository.get_dlq_event(topic=topic, partition=partition, offset=offset)
    assert isinstance(row, dict)
    assert row.get("event_id") == event_id
    assert row.get("attempts") == 3

