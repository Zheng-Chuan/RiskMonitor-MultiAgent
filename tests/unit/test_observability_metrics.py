import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from riskmonitor_multiagent.observability.metrics import (
    inc_counter,
    observe_ms,
    render_prometheus_metrics,
    reset_observability_metrics,
    set_gauge,
)


def test_observability_metrics_render_contains_counters_gauges_and_p95():
    reset_observability_metrics()
    inc_counter("rm_test_counter_total", labels={"a": "b"})
    set_gauge("rm_test_gauge", 1.23, labels={"x": "y"})
    observe_ms("rm_test_latency", 10.0, labels={"node": "n1"})
    observe_ms("rm_test_latency", 20.0, labels={"node": "n1"})

    out = render_prometheus_metrics()
    assert "rm_test_counter_total" in out
    assert "rm_test_gauge" in out
    assert "rm_test_latency_ms_p95" in out
    assert 'node="n1"' in out

