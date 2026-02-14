from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from riskmonitor_multiagent.governance.replay_compare import ReplayVariant, run_replay_compare


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--event-file", required=True)
    p.add_argument("--policy-a", required=True)
    p.add_argument("--policy-b", required=True)
    p.add_argument("--output", default="data/replay_compare/latest.json")
    args = p.parse_args()

    event = json.loads(Path(args.event_file).read_text(encoding="utf-8"))
    report = run_replay_compare(
        event=event,
        a=ReplayVariant(name="a", policy_version=args.policy_a),
        b=ReplayVariant(name="b", policy_version=args.policy_b),
        output_file=str(Path(args.output)),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

