#!/usr/bin/env python3
"""小规模评估，仅使用前 3 个用例来快速验证指标计算."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SCR_ROOT = _PROJECT_ROOT / "src"
for p in (_PROJECT_ROOT, _SCR_ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from eval.case_schema import load_benchmark_cases
from eval.gate import evaluate_quality_gate
from eval.report import save_report
from eval.runner import run_benchmark


async def main():
    parser = argparse.ArgumentParser(prog="quick_eval")
    parser.add_argument("--run-tag", type=str, default="quick_eval", help="运行标识")
    parser.add_argument("--num-cases", type=int, default=3, help="使用前 N 个用例")
    args = parser.parse_args()

    bench_path = _PROJECT_ROOT / "eval" / "benchmarks" / "explainability_cases.jsonl"
    cases = load_benchmark_cases(str(bench_path))
    
    print(f"=" * 80)
    print(f"小规模评估")
    print(f"=" * 80)
    print(f"总用例数: {len(cases)}")
    print(f"使用前 {args.num_cases} 个用例")
    
    # 只取前 N 个用例
    selected_cases = cases[:args.num_cases]
    print(f"选择的用例: {[c.case_id for c in selected_cases]}")
    
    config = {
        "hitl_auto_approve": True,
    }
    
    print(f"\n开始运行...")
    res = await run_benchmark(selected_cases, run_tag=args.run_tag, config=config, repeats=1)
    
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
    try:
        records = res.get("records") if isinstance(res, dict) else None
        reports_dir = _PROJECT_ROOT / "eval" / "reports"
        report_path = save_report(summary, args.run_tag, gate_output, records, output_dir=reports_dir)
    except Exception as e:
        print(f"警告: 报告生成失败: {e}", file=sys.stderr)
    
    print(f"\n" + "=" * 80)
    print(f"评估完成!")
    print(f"=" * 80)
    print(f"记录文件: {records_path}")
    print(f"汇总文件: {summary_path}")
    print(f"门禁文件: {gate_path}")
    if report_path:
        print(f"报告文件: {report_path}")
    
    print(f"\n门禁状态: {'✅ 通过' if gate.get('passed') else '❌ 未通过'}")
    print(f"通过率: {summary.get('pass_rate', 0):.2%}")
    
    agg = summary.get("aggregates", {})
    print(f"\n关键指标:")
    print(f"  步骤理由覆盖率: {agg.get('step_reason_coverage', 0):.2%}")
    print(f"  证据缺失率: {agg.get('evidence_missing_rate', 0):.2%}")
    print(f"  契约失败率: {agg.get('contract_fail_rate', 0):.2%}")
    print(f"  可解释性评分: {agg.get('explainability_score', 0):.2%}")
    print(f"  信息多样性 (IDS): {agg.get('ids_avg', 0):.2%}")
    print(f"  里程碑达成率: {agg.get('milestone_achieved_rate_avg', 0):.2%}")
    print(f"  任务完成度: {agg.get('task_completion_score_avg', 0):.2%}")
    print(f"  幻觉检测评分: {agg.get('hallucination_score_avg', 0):.2%}")
    print(f"  工具调用成功率: {agg.get('tool_call_success_rate_avg', 0):.2%}")
    print(f"  平均延迟: {agg.get('latency_ms_avg', 0):.0f} ms")
    print(f"  总 Token: {agg.get('tokens_total', 0)}")


if __name__ == "__main__":
    asyncio.run(main())
