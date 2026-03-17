#!/usr/bin/env python3
"""评估 runner：调度 case、执行业务流程、生成汇总、门禁检查和 Markdown 报告."""

import argparse
import asyncio
import json
import sys
from pathlib import Path


def list_available_metrics() -> None:
    """列出所有可用的指标及其分类."""
    metrics = {
        "基础指标": [
            ("total", "总用例数"),
            ("passed", "成功用例数"),
            ("failed", "失败用例数"),
            ("pass_rate", "通过率"),
            ("avg_latency_ms", "平均延迟（毫秒）"),
        ],
        "多Agent协作指标": [
            ("ids", "信息多样性分数（Information Diversity Score）"),
            ("upr", "冗余路径比（Unnecessary Path Ratio）"),
            ("milestone_rate", "里程碑达成率"),
            ("role_specialization", "角色专业化程度"),
            ("collaboration_efficiency", "协作效率"),
        ],
        "Agent系统指标": [
            ("task_completion_score", "任务完成质量评分"),
            ("hallucination_score", "幻觉检测评分"),
            ("tool_usage_efficiency", "工具使用效率"),
            ("error_recovery_rate", "错误恢复率"),
            ("plan_revision_count", "计划修正次数"),
            ("memory_system_efficiency", "记忆系统效能"),
        ],
        "P0/P1指标": [
            ("plan_execution_align_rate", "计划执行一致性"),
            ("tool_selection_accuracy", "工具选择准确率"),
            ("factuality_score", "事实准确性"),
            ("tool_result_utilization", "工具结果利用率"),
        ],
        "门禁指标": [
            ("gate_passed", "门禁是否通过"),
        ],
    }

    print("\n" + "=" * 80)
    print("可用指标列表")
    print("=" * 80)
    print()
    
    for category, metric_list in metrics.items():
        print(f"【{category}】")
        for metric_name, metric_desc in metric_list:
            print(f"  - {metric_name:<40} {metric_desc}")
        print()
    
    print("使用示例:")
    print("  --metrics pass_rate ids collaboration_efficiency")
    print("  --list-metrics")
    print("=" * 80)
    print()


def print_metrics_by_category(all_metrics: dict, selected_metrics: list[str] | None) -> None:
    """
    按分类打印指标.

    Args:
        all_metrics: 所有指标字典
        selected_metrics: 选择的指标列表，None 表示显示所有
    """
    metrics_categories = {
        "基础指标": [
            "total", "passed", "failed", "pass_rate", "avg_latency_ms"
        ],
        "多Agent协作指标": [
            "ids", "upr", "milestone_rate", "role_specialization", 
            "collaboration_efficiency"
        ],
        "Agent系统指标": [
            "task_completion_score", "hallucination_score", 
            "tool_usage_efficiency", "error_recovery_rate",
            "plan_revision_count", "memory_system_efficiency"
        ],
        "P0/P1指标": [
            "plan_execution_align_rate", "tool_selection_accuracy", 
            "factuality_score", "tool_result_utilization"
        ],
        "门禁指标": [
            "gate_passed"
        ],
    }

    print("\n" + "=" * 80)
    print("评估结果")
    print("=" * 80)
    print()

    for category, metric_names in metrics_categories.items():
        # 过滤出该分类下有值的指标
        available_metrics = []
        for name in metric_names:
            if name in all_metrics:
                if selected_metrics is None or name in selected_metrics:
                    available_metrics.append((name, all_metrics[name]))

        if available_metrics:
            print(f"【{category}】")
            for metric_name, metric_value in available_metrics:
                # 格式化输出
                if isinstance(metric_value, float):
                    if 0 <= metric_value <= 1:
                        # 百分比格式
                        print(f"  {metric_name:<40} {metric_value:.2%}")
                    else:
                        print(f"  {metric_name:<40} {metric_value:.2f}")
                elif isinstance(metric_value, bool):
                    status = "✅" if metric_value else "❌"
                    print(f"  {metric_name:<40} {status}")
                else:
                    print(f"  {metric_name:<40} {metric_value}")
            print()

    print("=" * 80)
    print()

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
    parser.add_argument("--cases", type=str, nargs="*", default=None, help="指定要运行的 case_id 列表，例如 --cases case1 case2")
    parser.add_argument("--metrics", type=str, nargs="*", default=None, help="指定要显示的指标列表，例如 --metrics pass_rate ids")
    parser.add_argument("--list-metrics", action="store_true", help="列出所有可用的指标及其分类")
    args = parser.parse_args()

    # 如果只需要列出指标
    if args.list_metrics:
        list_available_metrics()
        return 0

    # 加载测试用例
    cases = load_benchmark_cases(
        str(_PROJECT_ROOT / args.bench) if not Path(args.bench).is_absolute() else args.bench
    )

    # 过滤指定的 case
    if args.cases:
        cases = [c for c in cases if c.case_id in args.cases]
        if not cases:
            print(f"错误: 未找到指定的 case: {args.cases}", file=sys.stderr)
            return 1
        print(f"运行指定的 {len(cases)} 个 case: {[c.case_id for c in cases]}")

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
    }
    
    # 添加基础指标
    all_metrics = {}
    all_metrics["gate_passed"] = bool(gate.get("passed"))
    all_metrics.update(summary)
    
    # 如果指定了指标，只显示指定的指标
    if args.metrics:
        filtered_metrics = {}
        for metric in args.metrics:
            if metric in all_metrics:
                filtered_metrics[metric] = all_metrics[metric]
            else:
                print(f"警告: 未找到指标 '{metric}'", file=sys.stderr)
        output.update(filtered_metrics)
    else:
        # 否则显示所有指标
        output.update(all_metrics)
    
    if report_path:
        output["report_path"] = str(report_path)

    # 打印指标分类展示
    print_metrics_by_category(all_metrics, args.metrics)
    
    # 打印 JSON 结果
    print(json.dumps(output, ensure_ascii=False))

    # 返回退出码：门禁通过为 0，未通过为 1
    return 0 if bool(gate.get("passed")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
