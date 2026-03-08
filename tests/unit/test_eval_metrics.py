import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
for p in (_PROJECT_ROOT, _SRC_ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from eval.metrics import summarize_benchmark_records


def test_summarize_benchmark_records_aggregates_core_metrics():
    records = [
        {
            "case_id": "c1",
            "ok": True,
            "latency_ms": 100.0,
            "tokens_total": 10,
            "approval_required": False,
            "governance_blocked_count": 0,
            "degraded_count": 0,
            "quality": {
                "step_reason_coverage": 1.0,
                "evidence_missing_rate": 0.0,
                "receipt_binding_rate": 1.0,
                "contract_fail_rate": 0.0,
                "explainability_score": 1.0,
            },
        },
        {
            "case_id": "c1",
            "ok": False,
            "latency_ms": 200.0,
            "tokens_total": 20,
            "approval_required": True,
            "governance_blocked_count": 1,
            "degraded_count": 1,
            "quality": {
                "step_reason_coverage": 0.5,
                "evidence_missing_rate": 0.2,
                "receipt_binding_rate": 0.6,
                "contract_fail_rate": 0.1,
                "explainability_score": 0.7,
            },
        },
    ]

    s = summarize_benchmark_records(records)
    assert s.get("total_cases") == 2
    assert s.get("unique_cases") == 1
    assert s.get("pass_rate") == 0.5
    agg = s.get("aggregates") or {}
    assert agg.get("latency_ms_avg") == 150.0
    assert agg.get("tokens_total") == 30
    assert agg.get("step_reason_coverage") == 0.75
    assert agg.get("evidence_missing_rate") == 0.1
    assert agg.get("approval_required_rate") == 0.5
    assert agg.get("governance_blocked_avg") == 0.5
