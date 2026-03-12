#!/usr/bin/env python3
"""评估 runner：调度 case、执行业务流程、生成汇总、门禁检查和 Markdown 报告."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
# 评估流水线在仓库根 eval/，业务在 src/；两者解耦
for p in (_PROJECT_ROOT, _SRC_ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from eval.case_schema import load_benchmark_cases
from eval.gate import evaluate_quality_gate
from eval.report import save_report
from eval.runner import run_benchmark


def main() -> int:
    parser = argparse.ArgumentParser(prog="run_benchmark")
    parser.add_argument("--bench", type=str, required=True, help="Benchmark cases 文件路径")
    parser.add_argument("--run-tag", type=str, required=True, help="运行标识（用于输出文件命名）")
    parser.add_argument("--model", type=str, default=None, help="使用的 LLM 模型")
    parser.add_argument("--policy-version", type=str, default=None, help="策略版本")
    parser.add_argument("--prompt-version", type=str, default=None, help="提示版本")
    parser.add_argument("--hitl", type=int, default=1, help="是否自动审批 (1=是, 0=否)")
    parser.add_argument("--budget-profile", type=str, default=None, help="预算配置 (strict/balanced/loose)")
    parser.add_argument("--repeats", type=int, default=1, help="每个 case 重复运行次数")
    parser.add_argument("--no-report", action="store_true", help="不生成 Markdown 报告")
    args = parser.parse_args()

    # 加载测试用例
    cases = load_benchmark_cases(
        str(_PROJECT_ROOT / args.bench) if not Path(args.bench).is_absolute() else args.bench
    )

    # 构建运行配置
    config = {
        "model": args.model,
        "policy_version": args.policy_version,
        "prompt_version": args.prompt_version,
        "hitl_auto_approve": bool(args.hitl),
        "budget_profile": args.budget_profile,
    }

    # 执行 benchmark
    res = asyncio.run(run_benchmark(cases, run_tag=args.run_tag, config=config, repeats=max(1, int(args.repeats))))

    # 创建输出目录
    out_dir = _PROJECT_ROOT / "eval" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)

    # 保存原始记录
    records_path = out_dir / f"{args.run_tag}.jsonl"
    with records_path.open("w", encoding="utf-8") as f:
        for r in res.get("records") if isinstance(res, dict) else []:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # 保存汇总结果
    summary = res.get("summary") if isinstance(res, dict) else {}
    summary_path = out_dir / f"{args.run_tag}.summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    # 执行门禁检查
    gate = evaluate_quality_gate(summary)
    gate_output = {"run": args.run_tag, "gate": gate}
    gate_path = out_dir / f"{args.run_tag}.gate.json"
    gate_path.write_text(json.dumps(gate_output, ensure_ascii=False, indent=2), encoding="utf-8")

    # 生成 Markdown 报告
    report_path = None
    if not args.no_report:
        try:
            records = res.get("records") if isinstance(res, dict) else None
            reports_dir = _PROJECT_ROOT / "eval" / "reports"
            report_path = save_report(summary, args.run_tag, gate_output, records, output_dir=reports_dir)
        except Exception as e:
            print(f"警告: 报告生成失败: {e}", file=sys.stderr)

    # 输出结果摘要
    output = {
        "ok": True,
        "run_tag": args.run_tag,
        "records_path": str(records_path),
        "summary_path": str(summary_path),
        "gate_path": str(gate_path),
        "gate_passed": bool(gate.get("passed")),
        "pass_rate": summary.get("pass_rate", 0.0),
    }
    if report_path:
        output["report_path"] = str(report_path)

    print(json.dumps(output, ensure_ascii=False))

    # 返回退出码：门禁通过为 0，未通过为 1
    return 0 if bool(gate.get("passed")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
