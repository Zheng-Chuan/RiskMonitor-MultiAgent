#!/usr/bin/env python3

import argparse
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from riskmonitor_multiagent.knowledge.ingest import ingest_recent_alerts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--severity", type=str, default=None)
    parser.add_argument("--desk", type=str, default=None)
    args = parser.parse_args()

    result = ingest_recent_alerts(limit=int(args.limit), severity=args.severity, desk=args.desk)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

