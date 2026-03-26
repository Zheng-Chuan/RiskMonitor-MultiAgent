#!/usr/bin/env python3
"""
评估 CLI 工具.

Usage:
    python -m eval.cli run --cases all --output results/run_001.json
    python -m eval.cli run --category collaboration
    python -m eval.cli compare --current results/run_001.json --history results/run_000.json
    python -m eval.cli benchmark --result results/run_001.json
    python -m eval.cli report --result results/run_001.json --format html
    python -m eval.cli gate --run-id results/run_001.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

from eval.core.evaluator import Evaluator, EvaluationResult
from eval.core.report import ReportGenerator
from eval.comparison.benchmark import HistoryComparator, BenchmarkComparator

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False) -> None:
    """配置日志."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def load_all_cases(benchmarks_dir: str = "eval/benchmarks") -> list[Any]:
    """加载所有测试用例."""
    from eval.core.evaluator import TestCase
    
    cases: list[TestCase] = []
    benchmarks_path = Path(benchmarks_dir)
    
    if not benchmarks_path.exists():
        logger.error(f"Benchmarks directory not found: {benchmarks_dir}")
        return cases
    
    for jsonl_file in benchmarks_path.rglob("*.jsonl"):
        logger.info(f"Loading cases from {jsonl_file}")
        with open(jsonl_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    cases.append(TestCase.from_dict(data))
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse case: {e}")
    
    logger.info(f"Loaded {len(cases)} cases total")
    return cases


def filter_cases_by_category(cases: list[Any], category: str) -> list[Any]:
    """按类别过滤测试用例."""
    if category == "all":
        return cases
    return [c for c in cases if c.category == category]


async def run_workflow_runner(task: dict[str, Any]) -> dict[str, Any]:
    """
    工作流运行器.
    
    这是评估系统的核心入口,调用实际的 Agent 系统.
    """
    try:
        from riskmonitor_multiagent.orchestration.orchestrator_workflow import run_orchestrator_workflow
        
        result = await run_orchestrator_workflow(task=task)
        return {"ok": result.get("ok", False), "result": result}
    except Exception as e:
        logger.exception(f"Workflow execution failed: {e}")
        return {"ok": False, "error": str(e)}


async def cmd_run(args: argparse.Namespace) -> int:
    """运行评估."""
    setup_logging(args.verbose)
    
    cases = load_all_cases(args.benchmarks_dir)
    if not cases:
        logger.error("No test cases found")
        return 1
    
    cases = filter_cases_by_category(cases, args.category)
    if not cases:
        logger.error(f"No cases found for category: {args.category}")
        return 1
    
    if args.limit and args.limit > 0:
        cases = cases[:args.limit]
        logger.info(f"Limited to {len(cases)} cases")
    
    logger.info(f"Running evaluation with {len(cases)} cases")
    
    evaluator = Evaluator(
        model=args.model,
        llm_judge_enabled=not args.no_llm_judge,
    )
    
    config = {
        "model": args.model,
        "category": args.category,
        "llm_judge_enabled": not args.no_llm_judge,
    }
    
    result = await evaluator.run_evaluation(
        cases=cases,
        workflow_runner=run_workflow_runner,
        config=config,
    )
    
    output_path = Path(args.output) if args.output else Path(f"eval/results/{result.run_id}.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)
    
    logger.info(f"Evaluation result saved to {output_path}")
    
    print("\n" + "=" * 60)
    print("Evaluation Summary")
    print("=" * 60)
    print(f"Run ID: {result.run_id}")
    print(f"Total Cases: {result.total_cases}")
    print(f"Passed: {result.passed_cases}")
    print(f"Failed: {result.failed_cases}")
    print(f"Pass Rate: {result.pass_rate:.2%}")
    print(f"Overall Score: {result.overall_metrics.overall_score:.2%}")
    print("=" * 60)
    
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    """对比历史结果."""
    setup_logging(args.verbose)
    
    current_path = Path(args.current)
    if not current_path.exists():
        logger.error(f"Current result not found: {current_path}")
        return 1
    
    with open(current_path, "r", encoding="utf-8") as f:
        current_data = json.load(f)
    
    from eval.core.evaluator import EvaluationResult
    from eval.core.metrics import OverallMetrics
    
    current = EvaluationResult(
        run_id=current_data.get("run_id", ""),
        timestamp=current_data.get("timestamp", ""),
        config=current_data.get("config", {}),
        total_cases=current_data.get("summary", {}).get("total_cases", 0),
        passed_cases=current_data.get("summary", {}).get("passed_cases", 0),
        failed_cases=current_data.get("summary", {}).get("failed_cases", 0),
        overall_metrics=OverallMetrics(),
    )
    
    comparator = HistoryComparator()
    comparison = comparator.compare(current)
    
    print("\n" + "=" * 60)
    print("Comparison Results")
    print("=" * 60)
    
    if comparison.get("status") == "no_history":
        print("No history result found for comparison")
        return 0
    
    print(f"Current Run: {comparison['current_run_id']}")
    print(f"History Run: {comparison['history_run_id']}")
    print()
    
    print("Changes:")
    for name, change in comparison.get("changes", {}).items():
        sign = "+" if change["change"] >= 0 else ""
        print(f"  {name}: {change['current']:.4f} ({sign}{change['change']:.4f})")
    
    if comparison.get("improvements"):
        print("\nImprovements:")
        for imp in comparison["improvements"]:
            print(f"  ✅ {imp}")
    
    if comparison.get("regressions"):
        print("\nRegressions:")
        for reg in comparison["regressions"]:
            print(f"  ⚠️  {reg}")
    
    print("=" * 60)
    
    return 0


def cmd_benchmark(args: argparse.Namespace) -> int:
    """对比业界基准."""
    setup_logging(args.verbose)
    
    result_path = Path(args.result)
    if not result_path.exists():
        logger.error(f"Result not found: {result_path}")
        return 1
    
    with open(result_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    from eval.core.evaluator import EvaluationResult
    from eval.core.metrics import OverallMetrics
    
    result = EvaluationResult(
        run_id=data.get("run_id", ""),
        timestamp=data.get("timestamp", ""),
        config=data.get("config", {}),
        total_cases=data.get("summary", {}).get("total_cases", 0),
        passed_cases=data.get("summary", {}).get("passed_cases", 0),
        failed_cases=data.get("summary", {}).get("failed_cases", 0),
        overall_metrics=OverallMetrics(),
    )
    
    comparator = BenchmarkComparator()
    comparison = comparator.compare(result)
    
    print("\n" + "=" * 60)
    print("Benchmark Comparison")
    print("=" * 60)
    
    for bench_name, comp in comparison.get("comparisons", {}).items():
        print(f"\n{bench_name}:")
        print(f"  Source: {comp['source']}")
        better = comp["better_metrics_count"]
        total = comp["total_metrics"]
        status = "✅ Better" if comp["overall_better"] else "❌ Below"
        print(f"  Status: {status} ({better}/{total} metrics)")
        
        for metric, values in comp.get("metrics_comparison", {}).items():
            diff_sign = "+" if values["diff"] >= 0 else ""
            better_mark = "✓" if values["better"] else "✗"
            print(f"    {metric}: {values['ours']:.2f} vs {values['theirs']:.2f} ({diff_sign}{values['diff']:.2f}) {better_mark}")
    
    print("\n" + "=" * 60)
    print("Summary:")
    summary = comparison.get("summary", {})
    print(f"  Better than {summary.get('better_than_count', 0)}/{summary.get('total_benchmarks', 0)} benchmarks")
    print(f"  Performance Level: {summary.get('performance_level', 'Unknown')}")
    print("=" * 60)
    
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    """生成报告."""
    setup_logging(args.verbose)
    
    result_path = Path(args.result)
    if not result_path.exists():
        logger.error(f"Result not found: {result_path}")
        return 1
    
    with open(result_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    from eval.core.evaluator import EvaluationResult
    from eval.core.metrics import OverallMetrics
    
    result = EvaluationResult(
        run_id=data.get("run_id", ""),
        timestamp=data.get("timestamp", ""),
        config=data.get("config", {}),
        total_cases=data.get("summary", {}).get("total_cases", 0),
        passed_cases=data.get("summary", {}).get("passed_cases", 0),
        failed_cases=data.get("summary", {}).get("failed_cases", 0),
        overall_metrics=OverallMetrics(),
    )
    
    generator = ReportGenerator()
    
    output_path = Path(args.output) if args.output else result_path.with_suffix(f".{args.format}")
    
    if args.format == "json":
        generator.generate_json_report(result, output_path)
    elif args.format == "markdown" or args.format == "md":
        generator.generate_markdown_report(result, output_path)
    elif args.format == "html":
        generator.generate_html_report(result, output_path)
    else:
        logger.error(f"Unknown format: {args.format}")
        return 1
    
    print(f"Report generated: {output_path}")
    return 0


def cmd_gate(args: argparse.Namespace) -> int:
    """检查质量门禁."""
    setup_logging(args.verbose)
    
    # 加载评估结果
    result_path = Path(args.run_id)
    if not result_path.exists():
        # 尝试在 results 目录查找
        result_path = Path(f"eval/results/{args.run_id}.json")
    
    if not result_path.exists():
        logger.error(f"Result not found: {args.run_id}")
        return 1
    
    with open(result_path, "r", encoding="utf-8") as f:
        summary = json.load(f)
    
    # 加载门禁配置
    gate_config = Path(args.gate_config)
    if not gate_config.exists():
        logger.warning(f"Gate config not found: {gate_config}, using defaults")
        thresholds = {}
    else:
        from eval.gate import load_gate_thresholds
        thresholds = load_gate_thresholds(str(gate_config))
    
    # 执行门禁检查
    from eval.gate import evaluate_quality_gate, evaluate_with_custom_thresholds
    
    if thresholds:
        gate_result = evaluate_with_custom_thresholds(summary, thresholds)
    else:
        gate_result = evaluate_quality_gate(summary)
    
    # 输出结果
    print("\n" + "=" * 60)
    print("Quality Gate Check")
    print("=" * 60)
    
    if gate_result.passed:
        print("✅ 通过质量门禁")
    else:
        print("❌ 未通过质量门禁")
        print("\n失败原因:")
        for reason in gate_result.reasons:
            print(f"  - {reason}")
    
    print("\n指标摘要:")
    for metric, value in gate_result.metrics_summary.items():
        if isinstance(value, float):
            print(f"  {metric}: {value:.4f}")
        else:
            print(f"  {metric}: {value}")
    
    print("=" * 60)
    
    # 返回状态码 (0=通过,1=失败)
    return 0 if gate_result.passed else 1


def main() -> int:
    """主入口."""
    parser = argparse.ArgumentParser(
        description="Multi-Agent System Evaluation CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    run_parser = subparsers.add_parser("run", help="Run evaluation")
    run_parser.add_argument("--cases", default="all", help="Cases to run (default: all)")
    run_parser.add_argument("--category", default="all", help="Category filter (default: all)")
    run_parser.add_argument("--limit", type=int, default=0, help="Limit number of cases (default: 0 = no limit)")
    run_parser.add_argument("--output", "-o", help="Output file path")
    run_parser.add_argument("--model", help="Model to use")
    run_parser.add_argument("--no-llm-judge", action="store_true", help="Disable LLM judge")
    run_parser.add_argument("--benchmarks-dir", default="eval/benchmarks", help="Benchmarks directory")
    
    compare_parser = subparsers.add_parser("compare", help="Compare with history")
    compare_parser.add_argument("--current", required=True, help="Current result file")
    compare_parser.add_argument("--history", help="History result file (optional)")
    
    benchmark_parser = subparsers.add_parser("benchmark", help="Compare with benchmarks")
    benchmark_parser.add_argument("--result", required=True, help="Result file")
    
    report_parser = subparsers.add_parser("report", help="Generate report")
    report_parser.add_argument("--result", required=True, help="Result file")
    report_parser.add_argument("--format", choices=["json", "markdown", "md", "html"], default="html", help="Report format")
    report_parser.add_argument("--output", "-o", help="Output file path")
    
    gate_parser = subparsers.add_parser("gate", help="Check quality gate")
    gate_parser.add_argument("--run-id", required=True, help="Evaluation run ID or result file path")
    gate_parser.add_argument("--gate-config", default="eval/gates/default.json", help="Gate threshold config file")
    
    args = parser.parse_args()
    
    if args.command == "run":
        return asyncio.run(cmd_run(args))
    elif args.command == "compare":
        return cmd_compare(args)
    elif args.command == "benchmark":
        return cmd_benchmark(args)
    elif args.command == "report":
        return cmd_report(args)
    elif args.command == "gate":
        return cmd_gate(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
