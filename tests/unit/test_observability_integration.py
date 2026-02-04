import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from riskmonitor_multiagent.observability.metrics import inc_counter
from riskmonitor_multiagent.services.prometheus_metrics_service import generate_prometheus_metrics, reset_metrics


@pytest.mark.asyncio
async def test_metrics_endpoint_payload_includes_observability_block():
    reset_metrics()
    inc_counter("rm_test_counter_total")
    out = generate_prometheus_metrics()
    assert "rm_test_counter_total" in out
