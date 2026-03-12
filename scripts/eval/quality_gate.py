#!/usr/bin/env python3
"""质量门禁检查并生成评估报告."""

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
from eval.report import save_report


def main() -> int:
    parser = argparse.ArgumentParser(prog="quality_gate")
    parser.add_argument("--run", type=str, required=True, help="运行标识")
    parser.add_argument("--gate", type=str, default=None, help="自定义门禁配置文件路径")
    parser.add_argument("--no-report", action="store_true", help="不生成 Markdown 报告")
    args = parser.parse_args()

    results_dir = _PROJECT_ROOT / "eval" / "results"
    summary_path = results_dir / f"{args.run}.summary.json"
    if not summary_path.exists():
        raise FileNotFoundError(str(summary_path))

    # 加载汇总结果
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    # 加载自定义阈值（如果有）
    thresholds = None
    if args.gate is not None:
        gate_path = Path(args.gate)
        thresholds = json.loads(gate_path.read_text(encoding="utf-8"))

    # 执行门禁检查
    gate = evaluate_quality_gate(summary, thresholds=thresholds)
    out = {"run": args.run, "gate": gate}

    # 保存门禁结果
    gate_output_path = results_dir / f"{args.run}.gate.json"
    gate_output_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    # 生成 Markdown 报告
    report_path = None
    if not args.no_report:
        try:
            # 尝试加载 records
            records = None
            records_path = results_dir / f"{args.run}.jsonl"
            if records_path.exists():
                records = []
                for line in records_path.read_text(encoding="utf-8").strip().split("\n"):
                    if line.strip():
                        records.append(json.loads(line))

            # 指定报告输出目录为 eval/reports/
            reports_dir = _PROJECT_ROOT / "eval" / "reports"
            report_path = save_report(summary, args.run, out, records, output_dir=reports_dir)
        except Exception as e:
            print(f"警告: 报告生成失败: {e}", file=sys.stderr)

    # 输出结果
    output = {
        "ok": True,
        "gate_path": str(gate_output_path),
        "passed": bool(gate.get("passed")),
    }
    if report_path:
        output["report_path"] = str(report_path)

    print(json.dumps(output, ensure_ascii=False))

    # 返回退出码：通过为 0，未通过为 1
    return 0 if bool(gate.get("passed")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
