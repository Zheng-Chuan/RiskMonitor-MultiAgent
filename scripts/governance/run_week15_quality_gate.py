from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from riskmonitor_multiagent.governance.week15_quality_gate import QualityGateConfig, run_week15_quality_gate


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--cases", default="tests/fixtures/week15_cases.json")
    p.add_argument("--baseline", default="tests/fixtures/week15_baseline.json")
    p.add_argument("--write-baseline", action="store_true")
    p.add_argument("--enable-llm", action="store_true")
    args = p.parse_args()

    report = run_week15_quality_gate(
        config=QualityGateConfig(
            cases_file=str(Path(args.cases)),
            baseline_file=str(Path(args.baseline)),
            write_baseline=bool(args.write_baseline),
            disable_llm=not bool(args.enable_llm),
        )
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.get("ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
