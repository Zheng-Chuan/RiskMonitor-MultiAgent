from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from riskmonitor_multiagent.governance.regression import run_governance_regression


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--output", default="data/governance_regression/latest.json")
    args = p.parse_args()

    out = run_governance_regression(output_file=str(Path(args.output)))
    print(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if out.get("ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
