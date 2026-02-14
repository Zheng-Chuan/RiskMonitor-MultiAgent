import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from riskmonitor_multiagent.governance.regression import run_governance_regression


def test_governance_regression_runner_writes_output(tmp_path):
    out_file = tmp_path / "out.json"
    out = run_governance_regression(output_file=str(out_file))
    assert out.get("schema_version") == "governance_regression.v1"
    assert out.get("ok") is True
    assert out_file.exists()
    loaded = json.loads(out_file.read_text(encoding="utf-8"))
    assert loaded.get("ok") is True
    results = loaded.get("results")
    assert isinstance(results, list)
    assert {r.get("name") for r in results} >= {
        "rbac_deny",
        "approval_required",
        "approval_reject",
        "token_budget_exceeded",
        "tool_budget_exceeded",
        "timeout_budget_exceeded",
    }
    metrics = loaded.get("metrics")
    assert isinstance(metrics, str)
    assert "rm_rbac_denied_total" in metrics
    assert "rm_approval_required_total" in metrics
    assert "rm_budget_exceeded_total" in metrics
