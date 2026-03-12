"""评估报告生成器：将评估结果转换为格式清晰的 Markdown 报告.

报告输出位置：eval/reports/{run_tag}.md
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def _format_percent(value: float, decimals: int = 2) -> str:
    """格式化为百分比."""
    return f"{value * 100:.{decimals}f}%"


def _format_number(value: float, decimals: int = 2) -> str:
    """格式化数字."""
    return f"{value:.{decimals}f}"


def _format_duration(ms: float) -> str:
    """格式化毫秒为可读时间."""
    if ms < 1000:
        return f"{ms:.0f}ms"
    elif ms < 60000:
        return f"{ms / 1000:.1f}s"
    else:
        return f"{ms / 60000:.1f}min"


def _get_status_emoji(passed: bool) -> str:
    """获取状态表情."""
    return "✅" if passed else "❌"


def _get_trend_indicator(value: float, threshold: float, higher_is_better: bool = True) -> str:
    """获取趋势指示器."""
    if higher_is_better:
        if value >= threshold:
            return "🟢"
        elif value >= threshold * 0.8:
            return "🟡"
        else:
            return "🔴"
    else:
        if value <= threshold:
            return "🟢"
        elif value <= threshold * 1.2:
            return "🟡"
        else:
            return "🔴"


def generate_markdown_report(
    summary: dict[str, Any],
    gate_result: dict[str, Any] | None = None,
    records: list[dict[str, Any]] | None = None,
) -> str:
    """生成 Markdown 格式的评估报告.

    Args:
        summary: 评估汇总结果
        gate_result: 门禁检查结果（可选）
        records: 原始记录列表（可选，用于生成详细分析）

    Returns:
        Markdown 格式报告字符串
    """
    lines: list[str] = []

    # 报告标题
    run_tag = summary.get("run_tag", "unknown")
    lines.append(f"# RiskMonitor-MultiAgent 评估报告")
    lines.append(f"")
    lines.append(f"**运行标识**: `{run_tag}`")
    lines.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"")

    # 执行摘要
    lines.append(f"## 📊 执行摘要")
    lines.append(f"")

    total_cases = summary.get("total_cases", 0)
    unique_cases = summary.get("unique_cases", 0)
    pass_rate = summary.get("pass_rate", 0.0)
    duration_ms = summary.get("duration_ms", 0.0)

    agg = summary.get("aggregates", {})

    # 门禁状态
    gate_passed = gate_result.get("gate", {}).get("passed", False) if gate_result else None
    if gate_passed is not None:
        gate_emoji = _get_status_emoji(gate_passed)
        lines.append(f"| 指标 | 数值 |")
        lines.append(f"|------|------|")
        lines.append(f"| 门禁状态 | {gate_emoji} {'通过' if gate_passed else '未通过'} |")
        lines.append(f"| 测试用例数 | {total_cases} (去重: {unique_cases}) |")
        lines.append(f"| 通过率 | {_format_percent(pass_rate)} |")
        lines.append(f"| 总耗时 | {_format_duration(duration_ms)} |")
    else:
        lines.append(f"| 指标 | 数值 |")
        lines.append(f"|------|------|")
        lines.append(f"| 测试用例数 | {total_cases} (去重: {unique_cases}) |")
        lines.append(f"| 通过率 | {_format_percent(pass_rate)} |")
        lines.append(f"| 总耗时 | {_format_duration(duration_ms)} |")

    lines.append(f"")

    # 指标总览
    lines.append(f"## 📈 指标总览")
    lines.append(f"")

    # 配置信息
    config = summary.get("config", {})
    if config:
        lines.append(f"### 运行配置")
        lines.append(f"")
        lines.append(f"| 配置项 | 值 |")
        lines.append(f"|--------|-----|")
        if config.get("model"):
            lines.append(f"| 模型 | {config.get('model')} |")
        if config.get("policy_version"):
            lines.append(f"| 策略版本 | {config.get('policy_version')} |")
        if config.get("prompt_version"):
            lines.append(f"| 提示版本 | {config.get('prompt_version')} |")
        if config.get("hitl_auto_approve") is not None:
            lines.append(f"| 自动审批 | {'是' if config.get('hitl_auto_approve') else '否'} |")
        if config.get("budget_profile"):
            lines.append(f"| 预算配置 | {config.get('budget_profile')} |")
        lines.append(f"")

    # 基础性能指标
    lines.append(f"### 基础性能")
    lines.append(f"")
    lines.append(f"| 指标 | 数值 | 状态 |")
    lines.append(f"|------|------|------|")

    latency_avg = agg.get("latency_ms_avg", 0)
    latency_p95 = agg.get("latency_ms_p95", 0)
    tokens_total = agg.get("tokens_total", 0)

    lines.append(f"| 平均延迟 | {_format_number(latency_avg)} ms | 🟡 |")
    lines.append(f"| P95延迟 | {_format_number(latency_p95)} ms | 🟡 |")
    lines.append(f"| 总Token数 | {tokens_total:,} | 🟢 |")
    lines.append(f"")

    # 质量指标
    lines.append(f"### 质量与可解释性")
    lines.append(f"")
    lines.append(f"| 指标 | 数值 | 目标 | 状态 |")
    lines.append(f"|------|------|------|------|")

    step_reason = agg.get("step_reason_coverage", 0)
    evidence_missing = agg.get("evidence_missing_rate", 0)
    receipt_binding = agg.get("receipt_binding_rate", 0)
    contract_fail = agg.get("contract_fail_rate", 0)
    explainability = agg.get("explainability_score", 0)

    lines.append(f"| 步骤理由覆盖率 | {_format_percent(step_reason)} | ≥95% | {_get_trend_indicator(step_reason, 0.95)} |")
    lines.append(f"| 证据缺失率 | {_format_percent(evidence_missing)} | ≤5% | {_get_trend_indicator(evidence_missing, 0.05, higher_is_better=False)} |")
    lines.append(f"| Receipt绑定率 | {_format_percent(receipt_binding)} | ≥95% | {_get_trend_indicator(receipt_binding, 0.95)} |")
    lines.append(f"| 契约失败率 | {_format_percent(contract_fail)} | ≤2% | {_get_trend_indicator(contract_fail, 0.02, higher_is_better=False)} |")
    lines.append(f"| 可解释性评分 | {_format_percent(explainability)} | - | 🟢 |")
    lines.append(f"")

    # 治理安全指标
    lines.append(f"### 治理与安全")
    lines.append(f"")
    lines.append(f"| 指标 | 数值 | 说明 |")
    lines.append(f"|------|------|------|")

    approval_rate = agg.get("approval_required_rate", 0)
    governance_blocked = agg.get("governance_blocked_avg", 0)
    degraded_rate = agg.get("degraded_avg", 0)
    stability_rate = agg.get("stability_ok_rate", 0)

    lines.append(f"| 人工审批率 | {_format_percent(approval_rate)} | 需人工介入比例 |")
    lines.append(f"| 治理拦截数 | {_format_number(governance_blocked)} | 被策略拦截次数 |")
    lines.append(f"| 降级模式触发率 | {_format_percent(degraded_rate)} | 优雅降级频率 |")
    lines.append(f"| 稳定性通过率 | {_format_percent(stability_rate)} | 多次运行一致性 |")
    lines.append(f"")

    # 协作过程指标
    lines.append(f"### 协作与过程")
    lines.append(f"")
    lines.append(f"| 指标 | 数值 | 目标 | 说明 | 状态 |")
    lines.append(f"|------|------|------|------|------|")

    ids_avg = agg.get("ids_avg", 0)
    upr_avg = agg.get("upr_avg", 0)
    milestone_rate = agg.get("milestone_achieved_rate_avg", 0)

    lines.append(f"| 信息多样性 (IDS) | {_format_percent(ids_avg)} | ≥30% | 步骤间差异度 | {_get_trend_indicator(ids_avg, 0.30)} |")
    lines.append(f"| 冗余路径比 (UPR) | {_format_percent(upr_avg)} | ≤50% | 越低越好 | {_get_trend_indicator(upr_avg, 0.50, higher_is_better=False)} |")
    lines.append(f"| 里程碑达成率 | {_format_percent(milestone_rate)} | ≥75% | 关键阶段完成度 | {_get_trend_indicator(milestone_rate, 0.75)} |")
    lines.append(f"")

    # 新增的 Agent System Metrics（如果有）
    task_completion = agg.get("task_completion_score_avg")
    if task_completion is not None:
        lines.append(f"### Agent System Metrics")
        lines.append(f"")
        lines.append(f"| 指标 | 数值 | 目标 | 说明 | 状态 |")
        lines.append(f"|------|------|------|------|------|")

        hallucination = agg.get("hallucination_score_avg", 0)
        tool_success = agg.get("tool_call_success_rate_avg", 0)
        tool_efficiency = agg.get("tool_efficiency_score_avg", 0)
        error_recovery = agg.get("error_recovery_rate_avg", 0)
        plan_revision = agg.get("plan_revision_count_avg", 0)
        memory_efficiency = agg.get("memory_efficiency_score_avg", 0)

        lines.append(f"| 任务完成度 | {_format_percent(task_completion)} | ≥70% | 输出质量综合 | {_get_trend_indicator(task_completion, 0.70)} |")
        lines.append(f"| 幻觉检测评分 | {_format_percent(hallucination)} | ≥80% | 输出可信度 | {_get_trend_indicator(hallucination, 0.80)} |")
        lines.append(f"| 工具调用成功率 | {_format_percent(tool_success)} | ≥90% | 工具执行成功 | {_get_trend_indicator(tool_success, 0.90)} |")
        lines.append(f"| 工具效率得分 | {_format_percent(tool_efficiency)} | ≥70% | 综合效率 | {_get_trend_indicator(tool_efficiency, 0.70)} |")
        lines.append(f"| 错误恢复率 | {_format_percent(error_recovery)} | ≥80% | 容错能力 | {_get_trend_indicator(error_recovery, 0.80)} |")
        lines.append(f"| Plan修正次数 | {_format_number(plan_revision)} | ≤1.0 | 越低越好 | {_get_trend_indicator(plan_revision, 1.0, higher_is_better=False)} |")
        lines.append(f"| 记忆效能得分 | {_format_percent(memory_efficiency)} | ≥60% | 记忆系统效率 | {_get_trend_indicator(memory_efficiency, 0.60)} |")
        lines.append(f"")

    # 门禁检查结果
    if gate_result and gate_result.get("gate"):
        gate = gate_result.get("gate", {})
        lines.append(f"## 🚪 门禁检查结果")
        lines.append(f"")

        gate_passed = gate.get("passed", False)
        gate_emoji = _get_status_emoji(gate_passed)
        lines.append(f"**状态**: {gate_emoji} {'通过' if gate_passed else '未通过'}")
        lines.append(f"")

        reasons = gate.get("reasons", [])
        if reasons:
            lines.append(f"**未通过原因**:")
            lines.append(f"")
            for reason in reasons:
                # 转换原因代码为可读文本
                readable_reason = _translate_gate_reason(reason)
                lines.append(f"- ❌ {readable_reason}")
            lines.append(f"")

        # 阈值对比表
        observed = gate.get("observed", {})
        thresholds = gate.get("thresholds", {})

        if observed and thresholds:
            lines.append(f"### 详细阈值对比")
            lines.append(f"")
            lines.append(f"| 指标 | 观测值 | 阈值 | 状态 |")
            lines.append(f"|------|--------|------|------|")

            # 定义指标展示顺序和配置
            metric_configs = [
                ("step_reason_coverage", "步骤理由覆盖率", True, 0.95),
                ("evidence_missing_rate", "证据缺失率", False, 0.05),
                ("receipt_binding_rate", "Receipt绑定率", True, 0.95),
                ("contract_fail_rate", "契约失败率", False, 0.02),
                ("latency_ms_p95", "P95延迟", False, 8000.0, "ms"),
                ("tokens_total", "总Token数", False, 50000.0, ""),
                ("stability_ok_rate", "稳定性通过率", True, 1.0),
                ("ids_avg", "信息多样性(IDS)", True, 0.3),
                ("upr_avg", "冗余路径比(UPR)", False, 0.5),
                ("milestone_achieved_rate_avg", "里程碑达成率", True, 0.75),
                ("task_completion_score_avg", "任务完成度", True, 0.7),
                ("hallucination_score_avg", "幻觉检测评分", True, 0.8),
                ("tool_call_success_rate_avg", "工具调用成功率", True, 0.9),
                ("tool_efficiency_score_avg", "工具效率得分", True, 0.7),
                ("error_recovery_rate_avg", "错误恢复率", True, 0.8),
                ("plan_revision_count_avg", "Plan修正次数", False, 1.0),
                ("memory_efficiency_score_avg", "记忆效能得分", True, 0.6),
            ]

            for config in metric_configs:
                key = config[0]
                label = config[1]
                higher_is_better = config[2]
                threshold = config[3]
                unit = config[4] if len(config) > 4 else None

                if key in observed:
                    value = observed[key]
                    threshold_key = f"{'min' if higher_is_better else 'max'}_{key}"
                    actual_threshold = thresholds.get(threshold_key, threshold)

                    # 格式化数值
                    if key in ["latency_ms_p95"]:
                        value_str = f"{_format_number(value)} ms"
                        threshold_str = f"{_format_number(actual_threshold)} ms"
                    elif key in ["tokens_total"]:
                        value_str = f"{int(value):,}"
                        threshold_str = f"{int(actual_threshold):,}"
                    elif key in ["plan_revision_count_avg"]:
                        value_str = _format_number(value)
                        threshold_str = _format_number(actual_threshold)
                    else:
                        value_str = _format_percent(value)
                        threshold_str = _format_percent(actual_threshold)

                    status = "✅" if (value >= actual_threshold if higher_is_better else value <= actual_threshold) else "❌"
                    lines.append(f"| {label} | {value_str} | {threshold_str} | {status} |")

            lines.append(f"")

    # 改进建议
    if gate_result and not gate_passed:
        lines.append(f"## 💡 改进建议")
        lines.append(f"")

        suggestions = _generate_improvement_suggestions(gate.get("reasons", []))
        for suggestion in suggestions:
            lines.append(f"- {suggestion}")
        lines.append(f"")

    # 页脚
    lines.append(f"---")
    lines.append(f"")
    lines.append(f"*报告由 RiskMonitor-MultiAgent 评估流水线自动生成*")

    return "\n".join(lines)


def _translate_gate_reason(reason: str) -> str:
    """将门禁原因代码翻译为可读文本."""
    translations = {
        "step_reason_coverage_below_threshold": "步骤理由覆盖率低于阈值",
        "evidence_missing_rate_above_threshold": "证据缺失率高于阈值",
        "receipt_binding_rate_below_threshold": "Receipt绑定率低于阈值",
        "contract_fail_rate_above_threshold": "契约失败率高于阈值",
        "latency_ms_p95_above_threshold": "P95延迟高于阈值",
        "tokens_total_above_threshold": "总Token数高于阈值",
        "stability_ok_rate_below_threshold": "稳定性通过率低于阈值",
        "ids_avg_below_threshold": "信息多样性(IDS)低于阈值",
        "upr_avg_above_threshold": "冗余路径比(UPR)高于阈值",
        "milestone_achieved_rate_avg_below_threshold": "里程碑达成率低于阈值",
        "task_completion_score_avg_below_threshold": "任务完成度评分低于阈值",
        "hallucination_score_avg_below_threshold": "幻觉检测评分低于阈值",
        "tool_call_success_rate_avg_below_threshold": "工具调用成功率低于阈值",
        "tool_efficiency_score_avg_below_threshold": "工具效率得分低于阈值",
        "error_recovery_rate_avg_below_threshold": "错误恢复率低于阈值",
        "plan_revision_count_avg_above_threshold": "Plan修正次数高于阈值",
        "memory_efficiency_score_avg_below_threshold": "记忆效能得分低于阈值",
    }
    return translations.get(reason, reason)


def _generate_improvement_suggestions(reasons: list[str]) -> list[str]:
    """基于未通过原因生成改进建议."""
    suggestions = []

    reason_to_suggestion = {
        "step_reason_coverage_below_threshold": "优化 Orchestrator Agent 的提示词，确保每个 Plan 步骤都包含详细的理由说明",
        "evidence_missing_rate_above_threshold": "加强各 Agent 的证据引用能力，确保输出结论都有相应的证据支持",
        "receipt_binding_rate_below_threshold": "改进命令执行与回执绑定的逻辑，确保工具调用结果正确关联",
        "contract_fail_rate_above_threshold": "严格输出格式校验，添加更完善的 Schema 验证和自动修复机制",
        "latency_ms_p95_above_threshold": "考虑启用流式响应、优化 LLM 调用策略或增加缓存机制",
        "tokens_total_above_threshold": "优化提示词长度，启用上下文压缩或使用更高效的模型",
        "stability_ok_rate_below_threshold": "检查 Agent 随机性问题，添加结果确定性验证机制",
        "ids_avg_below_threshold": "鼓励不同 Agent 从不同视角分析问题，增加步骤间信息多样性",
        "upr_avg_above_threshold": "优化 Plan 执行效率，减少不必要的步骤和降级触发",
        "milestone_achieved_rate_avg_below_threshold": "确保各阶段 Agent 正常输出，检查中间步骤失败原因",
        "task_completion_score_avg_below_threshold": "提升输出完整性和意图匹配度，确保任务被充分执行",
        "hallucination_score_avg_below_threshold": "加强事实核查机制，确保所有结论都有证据支持",
        "tool_call_success_rate_avg_below_threshold": "检查工具接口稳定性，优化错误处理和重试机制",
        "tool_efficiency_score_avg_below_threshold": "减少不必要的工具调用，优化工具选择策略",
        "error_recovery_rate_avg_below_threshold": "增强错误恢复能力，添加更多容错处理逻辑",
        "plan_revision_count_avg_above_threshold": "优化初始 Plan 质量，减少因质量问题导致的重规划",
        "memory_efficiency_score_avg_below_threshold": "检查记忆系统配置，优化 Redis 和 PageIndex 使用效率",
    }

    for reason in reasons:
        suggestion = reason_to_suggestion.get(reason, f"需要关注和改进: {reason}")
        suggestions.append(suggestion)

    return suggestions


def save_report(
    summary: dict[str, Any],
    run_tag: str,
    gate_result: dict[str, Any] | None = None,
    records: list[dict[str, Any]] | None = None,
    output_dir: str | Path | None = None,
) -> Path:
    """生成并保存 Markdown 报告.

    Args:
        summary: 评估汇总结果
        run_tag: 运行标识
        gate_result: 门禁检查结果（可选）
        records: 原始记录列表（可选）
        output_dir: 输出目录，默认为 eval/reports/

    Returns:
        报告文件路径
    """
    if output_dir is None:
        output_dir = Path(__file__).resolve().parents[1] / "reports"
    else:
        output_dir = Path(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    report_path = output_dir / f"{run_tag}.md"

    markdown = generate_markdown_report(summary, gate_result, records)
    report_path.write_text(markdown, encoding="utf-8")

    return report_path


def load_and_generate_report(
    run_tag: str,
    results_dir: str | Path | None = None,
    output_dir: str | Path | None = None,
) -> Path:
    """从已有结果文件加载并生成报告.

    Args:
        run_tag: 运行标识
        results_dir: 结果文件目录，默认为 eval/results/
        output_dir: 报告输出目录，默认为 eval/reports/

    Returns:
        报告文件路径
    """
    if results_dir is None:
        results_dir = Path(__file__).resolve().parents[1] / "results"
    else:
        results_dir = Path(results_dir)

    # 加载 summary
    summary_path = results_dir / f"{run_tag}.summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    # 尝试加载 gate 结果
    gate_result = None
    gate_path = results_dir / f"{run_tag}.gate.json"
    if gate_path.exists():
        gate_result = json.loads(gate_path.read_text(encoding="utf-8"))

    # 尝试加载 records（可选，用于详细分析）
    records = None
    records_path = results_dir / f"{run_tag}.jsonl"
    if records_path.exists():
        records = []
        for line in records_path.read_text(encoding="utf-8").strip().split("\n"):
            if line.strip():
                records.append(json.loads(line))

    return save_report(summary, run_tag, gate_result, records, output_dir)


if __name__ == "__main__":
    # 命令行用法: python -m eval.report <run_tag>
    import sys

    if len(sys.argv) < 2:
        print("用法: python -m eval.report <run_tag>")
        print("示例: python -m eval.report final")
        sys.exit(1)

    run_tag = sys.argv[1]
    report_path = load_and_generate_report(run_tag)
    print(f"报告已生成: {report_path}")
