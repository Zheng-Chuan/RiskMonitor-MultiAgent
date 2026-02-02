import base64
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from riskmonitor_multiagent.sentinel.service import MAX_EXPOSURE_THRESHOLD, SentinelService


class _Msg:
    def __init__(self, value):
        self.value = value


def _encode_decimal(value: float, scale: int = 4) -> str:
    unscaled = int(round(value * (10**scale)))
    length = max(1, (unscaled.bit_length() + 8) // 8)
    raw = unscaled.to_bytes(length, byteorder="big", signed=True)
    return base64.b64encode(raw).decode("ascii")


@pytest.mark.asyncio
async def test_process_message_triggers_alert_for_schema_payload_decimal():
    svc = SentinelService()
    called = {}

    async def _trigger_alert(*, desk: str, exposure: float, record: dict):
        called["desk"] = desk
        called["exposure"] = exposure
        called["record"] = record

    svc._trigger_alert = _trigger_alert  # type: ignore[attr-defined]

    msg = _Msg(
        {
            "schema": {"type": "struct"},
            "payload": {
                "desk": "Commodities",
                "delta": _encode_decimal(MAX_EXPOSURE_THRESHOLD + 1.0),
                "__op": "u",
                "__ts_ms": 123,
            },
        }
    )

    await svc._process_message(msg)

    assert called["desk"] == "Commodities"
    assert called["exposure"] > MAX_EXPOSURE_THRESHOLD


@pytest.mark.asyncio
async def test_process_message_handles_envelope_after_format():
    svc = SentinelService()
    called = {}

    async def _trigger_alert(*, desk: str, exposure: float, record: dict):
        called["desk"] = desk
        called["exposure"] = exposure

    svc._trigger_alert = _trigger_alert  # type: ignore[attr-defined]

    msg = _Msg(
        {
            "payload": {
                "op": "u",
                "after": {"desk": "Equity Derivatives", "delta": MAX_EXPOSURE_THRESHOLD + 10.0},
            }
        }
    )

    await svc._process_message(msg)

    assert called["desk"] == "Equity Derivatives"
    assert called["exposure"] > MAX_EXPOSURE_THRESHOLD
