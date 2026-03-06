import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from riskmonitor_multiagent.eval.gate import evaluate_quality_gate


def test_quality_gate_passes_when_metrics_meet_thresholds():
    summary = {
        "aggregates": {
            "step_reason_coverage": 1.0,
            "evidence_missing_rate": 0.0,
            "receipt_binding_rate": 1.0,
            "contract_fail_rate": 0.0,
            "latency_ms_p95": 1000.0,
            "tokens_total": 1000,
            "stability_ok_rate": 1.0,
        }
    }
    out = evaluate_quality_gate(summary)
    assert out.get("passed") is True
    assert out.get("reasons") == []


def test_quality_gate_blocks_on_evidence_missing():
    summary = {
        "aggregates": {
            "step_reason_coverage": 1.0,
            "evidence_missing_rate": 0.3,
            "receipt_binding_rate": 1.0,
            "contract_fail_rate": 0.0,
            "latency_ms_p95": 1000.0,
            "tokens_total": 1000,
            "stability_ok_rate": 1.0,
        }
    }
    out = evaluate_quality_gate(summary)
    assert out.get("passed") is False
    assert "evidence_missing_rate_above_threshold" in (out.get("reasons") or [])
