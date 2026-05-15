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
import hashlib
import asyncio
import json
import logging
import sys
from pathlib import Path

from eval.core.evaluator import Evaluator, EvaluationResult
from eval.core.report import ReportGenerator
from eval.comparison.benchmark import HistoryComparator, BenchmarkComparator

logger = logging.getLogger(__name__)
_PRIMARY_BENCHMARK_CATEGORIES = {"simple", "medium", "complex", "recovery", "approval", "memory", "safety"}
_PRIMARY_BENCHMARK_FILES = {
    "simple": "queries.jsonl",
    "medium": "analysis.jsonl",
    "complex": "multi_step.jsonl",
    "recovery": "recovery.jsonl",
    "approval": "approval.jsonl",
    "memory": "memory.jsonl",
    "safety": "safety.jsonl",
}


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
    
    jsonl_files = list(benchmarks_path.rglob("*.jsonl"))
    category_dirs = {
        jsonl_file.parent.name
        for jsonl_file in jsonl_files
    }
    if _PRIMARY_BENCHMARK_CATEGORIES.issubset(category_dirs):
        jsonl_files = [
            jsonl_file
            for jsonl_file in jsonl_files
            if jsonl_file.parent.name in _PRIMARY_BENCHMARK_CATEGORIES
            and jsonl_file.name == _PRIMARY_BENCHMARK_FILES.get(jsonl_file.parent.name)
        ]

    for jsonl_file in jsonl_files:
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
        await _bootstrap_eval_memory(task)
        from riskmonitor_multiagent.orchestration.proactive_workflow import run_proactive_workflow
        
        return await run_proactive_workflow(task=task)
    except Exception as e:
        logger.exception(f"Workflow execution failed: {e}")
        return {"ok": False, "error": str(e)}


async def _bootstrap_eval_memory(task: dict[str, Any]) -> None:
    """为 memory 类 benchmark 注入轻量历史经验."""
    benchmark_config = task.get("benchmark_config") if isinstance(task.get("benchmark_config"), dict) else {}
    if benchmark_config.get("category") != "memory":
        return
    if task.get("memory_enabled", True) is not True:
        return

    from riskmonitor_multiagent.memory import get_memory_store

    memory_store = get_memory_store()
    run_id = str(task.get("task_id") or "eval_bootstrap")
    session_id = task.get("session_id") if isinstance(task.get("session_id"), str) else None
    payload = task.get("payload") if isinstance(task.get("payload"), dict) else {}
    content = payload.get("content") if isinstance(payload.get("content"), str) else ""
    if not content and isinstance(task.get("content"), str):
        content = task.get("content") or ""
    bootstrap_entry = {
        "agent_id": "critic",
        "scope": "shared",
        "kind": "semantic_case",
        "memory_type": "semantic",
        "session_id": session_id,
        "run_id": run_id,
        "source": "eval_memory_bootstrap",
        "created_by": "evaluator",
        "agent_role": "critic",
        "agent_perspective": "quality_gate",
        "task_phase": "planning",
        "confidence": 0.95,
        "trace_ref": {"run_id": run_id, "kind": "bootstrap"},
        "content": {
            "text": f"历史 lesson 表明 延迟异常应先复用已验证的排查路径 并给出建议. {content}".strip(),
            "agent_perspective": "quality_gate",
            "decision_pattern": "先引用历史 lesson -> 再核对当前延迟异常 -> 最后输出建议",
            "applicable_conditions": ["延迟异常", "lesson_reuse", "memory_benchmark"],
            "failure_boundary": ["无历史 lesson 时不要伪造经验", "缺少证据时只输出保守建议"],
            "evidence_refs": [f"bootstrap:{run_id}"],
            "snapshot_text": "delay lesson reuse bootstrap",
        },
        "tags": ["experience", "few_shot", "bootstrap"],
    }
    await memory_store.append(bootstrap_entry)


def _build_eval_task(task: dict[str, Any], *, baseline_mode: str, memory_enabled: bool, benchmark_config: dict[str, Any]) -> dict[str, Any]:
    """为评测运行构造任务."""
    built = dict(task)
    payload = dict(built.get("payload")) if isinstance(built.get("payload"), dict) else {}
    if not isinstance(payload.get("content"), str) and isinstance(built.get("content"), str):
        payload["content"] = built.get("content")
    if not isinstance(payload.get("type"), str) and isinstance(built.get("type"), str):
        payload["type"] = built.get("type")
    if not isinstance(payload.get("context"), dict) and isinstance(built.get("context"), dict):
        payload["context"] = dict(built.get("context") or {})
    if payload:
        built["payload"] = payload

    task_id = built.get("task_id")
    if not isinstance(task_id, str) or not task_id.strip():
        signature = json.dumps(
            {
                "content": payload.get("content"),
                "type": payload.get("type"),
                "context": payload.get("context"),
                "baseline_mode": baseline_mode,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        task_id = f"eval_{hashlib.md5(signature.encode('utf-8')).hexdigest()[:12]}"
        built["task_id"] = task_id
    if not isinstance(built.get("session_id"), str) or not str(built.get("session_id")).strip():
        built["session_id"] = f"eval_session:{task_id}"

    built["memory_enabled"] = memory_enabled
    built["private_memory_enabled"] = memory_enabled and baseline_mode != "private_disabled"
    built["baseline_mode"] = baseline_mode
    built["category"] = built.get("category") or benchmark_config.get("category")
    built["benchmark_config"] = dict(benchmark_config)
    built["benchmark_config"]["category"] = built.get("category") or benchmark_config.get("category")
    if baseline_mode == "single_agent":
        # 先把 baseline 模式显式打到任务里 便于 trace 和报告复现实验
        built["single_agent_mode"] = True
    return built


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

    memory_enabled = args.baseline_mode != "memory_off" and not args.disable_memory
    private_memory_enabled = memory_enabled and args.baseline_mode != "private_disabled"
    config = {
        "model": args.model,
        "category": args.category,
        "llm_judge_enabled": not args.no_llm_judge,
        "baseline_mode": args.baseline_mode,
        "memory_enabled": memory_enabled,
        "private_memory_enabled": private_memory_enabled,
        "dataset_version": args.dataset_version,
        "benchmark_config": {
            "category": args.category,
            "dataset_version": args.dataset_version,
            "baseline_mode": args.baseline_mode,
            "memory_enabled": memory_enabled,
            "private_memory_enabled": private_memory_enabled,
        },
    }

    async def _workflow_runner(task: dict[str, Any]) -> dict[str, Any]:
        eval_task = _build_eval_task(
            task,
            baseline_mode=args.baseline_mode,
            memory_enabled=memory_enabled,
            benchmark_config=config["benchmark_config"],
        )
        return await run_workflow_runner(eval_task)

    result = await evaluator.run_evaluation(
        cases=cases,
        workflow_runner=_workflow_runner,
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


def cmd_baseline_compare(args: argparse.Namespace) -> int:
    """对比主系统和 baseline 结果."""
    setup_logging(args.verbose)

    primary_path = Path(args.primary)
    baseline_path = Path(args.baseline)
    if not primary_path.exists():
        logger.error(f"Primary result not found: {primary_path}")
        return 1
    if not baseline_path.exists():
        logger.error(f"Baseline result not found: {baseline_path}")
        return 1

    with open(primary_path, "r", encoding="utf-8") as f:
        primary = json.load(f)
    with open(baseline_path, "r", encoding="utf-8") as f:
        baseline = json.load(f)

    primary_metrics = primary.get("behavior_metrics", {})
    baseline_metrics = baseline.get("behavior_metrics", {})
    tracked_metrics = [
        "task_success_rate",
        "tool_success_rate",
        "tool_selection_accuracy",
        "receipt_binding_rate",
        "approval_correctness",
        "replan_success_rate",
        "memory_hit_rate",
        "memory_usefulness",
        "resume_success_rate",
        "few_shot_reuse_rate",
        "role_drift_rate",
        "memory_cross_talk_rate",
        "dangerous_action_block_rate",
        "message_trace_completeness",
        "factuality_score",
        "evidence_coverage",
    ]

    print("\n" + "=" * 60)
    print("Baseline Comparison")
    print("=" * 60)
    print(f"Primary: {primary_path}")
    print(f"Baseline: {baseline_path}")
    print()

    for metric_name in tracked_metrics:
        primary_value = float(primary_metrics.get(metric_name, 0.0))
        baseline_value = float(baseline_metrics.get(metric_name, 0.0))
        diff = primary_value - baseline_value
        sign = "+" if diff >= 0 else ""
        print(f"{metric_name}: {primary_value:.4f} vs {baseline_value:.4f} ({sign}{diff:.4f})")

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

    if gate_result.warnings:
        print("\n告警项:")
        for warning in gate_result.warnings:
            print(f"  - {warning}")
    
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
    run_parser.add_argument("--baseline-mode", choices=["primary", "single_agent", "memory_off", "private_disabled"], default="primary", help="Baseline mode")
    run_parser.add_argument("--disable-memory", action="store_true", help="Disable memory regardless of baseline mode")
    run_parser.add_argument("--dataset-version", default="benchmark.v2", help="Dataset version tag")
    
    compare_parser = subparsers.add_parser("compare", help="Compare with history")
    compare_parser.add_argument("--current", required=True, help="Current result file")
    compare_parser.add_argument("--history", help="History result file (optional)")

    baseline_compare_parser = subparsers.add_parser("baseline-compare", help="Compare with baseline result")
    baseline_compare_parser.add_argument("--primary", required=True, help="Primary result file")
    baseline_compare_parser.add_argument("--baseline", required=True, help="Baseline result file")
    
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
    elif args.command == "baseline-compare":
        return cmd_baseline_compare(args)
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
