#!/usr/bin/env python3

import argparse
import asyncio
import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from riskmonitor_multiagent.eval.case_schema import load_benchmark_cases
from riskmonitor_multiagent.eval.runner import run_benchmark


def main() -> int:
    parser = argparse.ArgumentParser(prog="run_benchmark")
    parser.add_argument("--bench", type=str, required=True)
    parser.add_argument("--run-tag", type=str, required=True)
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--policy-version", type=str, default=None)
    parser.add_argument("--prompt-version", type=str, default=None)
    parser.add_argument("--hitl", type=int, default=1)
    parser.add_argument("--budget-profile", type=str, default=None)
    parser.add_argument("--repeats", type=int, default=1)
    args = parser.parse_args()

    cases = load_benchmark_cases(args.bench)
    config = {
        "model": args.model,
        "policy_version": args.policy_version,
        "prompt_version": args.prompt_version,
        "hitl_auto_approve": bool(args.hitl),
        "budget_profile": args.budget_profile,
    }

    res = asyncio.run(run_benchmark(cases, run_tag=args.run_tag, config=config, repeats=max(1, int(args.repeats))))
    out_dir = _PROJECT_ROOT / "eval" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)

    records_path = out_dir / f"{args.run_tag}.jsonl"
    summary_path = out_dir / f"{args.run_tag}.summary.json"

    with records_path.open("w", encoding="utf-8") as f:
        for r in res.get("records") if isinstance(res, dict) else []:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    summary = res.get("summary") if isinstance(res, dict) else {}
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "records_path": str(records_path), "summary_path": str(summary_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
