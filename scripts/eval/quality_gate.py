#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
for p in (_PROJECT_ROOT, _SRC_ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from eval.gate import evaluate_quality_gate


def main() -> int:
    parser = argparse.ArgumentParser(prog="quality_gate")
    parser.add_argument("--run", type=str, required=True)
    parser.add_argument("--gate", type=str, default=None)
    args = parser.parse_args()

    results_dir = _PROJECT_ROOT / "eval" / "results"
    summary_path = results_dir / f"{args.run}.summary.json"
    if not summary_path.exists():
        raise FileNotFoundError(str(summary_path))

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    thresholds = None
    if args.gate is not None:
        gate_path = Path(args.gate)
        thresholds = json.loads(gate_path.read_text(encoding="utf-8"))

    gate = evaluate_quality_gate(summary, thresholds=thresholds)
    out = {"run": args.run, "gate": gate}
    out_path = results_dir / f"{args.run}.gate.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "gate_path": str(out_path), "passed": bool(gate.get("passed"))}, ensure_ascii=False))
    return 0 if bool(gate.get("passed")) else 1


if __name__ == "__main__":
    raise SystemExit(main())

