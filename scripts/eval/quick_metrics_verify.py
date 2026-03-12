#!/usr/bin/env python3
"""快速验证新指标计算逻辑."""

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
for p in (_PROJECT_ROOT, _SRC_ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from eval.metrics import summarize_benchmark_records
from eval.gate import evaluate_quality_gate


def create_mock_records() -> list[dict]:
    """创建模拟的评估记录来测试新指标."""
    return [
        {
            "case_id": "test_001",
            "run_tag": "verify",
            "repeat_index": 0,
            "tags": ["explainability", "read_only"],
            "ok": True,
            "latency_ms": 1500.0,
            "tokens_total": 2500,
            "approval_required": False,
            "governance_blocked_count": 0,
            "degraded_count": 0,
            "evidence_missing_steps": [],
            # 原有指标
            "ids_score": 0.65,
            "upr": 0.2,
            "milestone_achieved_rate": 0.85,
            # 新增指标
            "task_completion_score": 0.82,
            "hallucination_score": 0.91,
            "tool_call_success_rate": 0.95,
            "tool_call_count": 2.0,
            "tool_efficiency_score": 0.88,
            "error_recovery_rate": 1.0,
            "plan_revision_count": 0.0,
            "memory_usage_rate": 0.75,
            "context_completeness": 0.8,
            "memory_efficiency_score": 0.77,
            "quality": {
                "step_reason_coverage": 0.95,
                "evidence_missing_rate": 0.05,
                "receipt_binding_rate": 0.98,
                "contract_fail_rate": 0.02,
                "explainability_score": 0.88,
                # 新增指标在quality中
                "ids_score": 0.65,
                "upr": 0.2,
                "milestone_achieved_rate": 0.85,
                "task_completion_score": 0.82,
                "hallucination_score": 0.91,
                "tool_efficiency_score": 0.88,
                "error_recovery_rate": 1.0,
                "plan_revision_count": 0.0,
                "memory_efficiency_score": 0.77,
            },
            "config": {
                "policy_version": "v1",
                "prompt_version": "v1",
                "model": "test-model",
            },
        },
        {
            "case_id": "test_002",
            "run_tag": "verify",
            "repeat_index": 0,
            "tags": ["approval", "side_effect"],
            "ok": True,
            "latency_ms": 2300.0,
            "tokens_total": 3200,
            "approval_required": True,
            "governance_blocked_count": 1,
            "degraded_count": 0,
            "evidence_missing_steps": [],
            # 原有指标
            "ids_score": 0.55,
            "upr": 0.35,
            "milestone_achieved_rate": 0.75,
            # 新增指标
            "task_completion_score": 0.78,
            "hallucination_score": 0.85,
            "tool_call_success_rate": 0.90,
            "tool_call_count": 3.0,
            "tool_efficiency_score": 0.82,
            "error_recovery_rate": 1.0,
            "plan_revision_count": 1.0,
            "memory_usage_rate": 0.70,
            "context_completeness": 0.75,
            "memory_efficiency_score": 0.72,
            "quality": {
                "step_reason_coverage": 0.90,
                "evidence_missing_rate": 0.08,
                "receipt_binding_rate": 0.95,
                "contract_fail_rate": 0.05,
                "explainability_score": 0.82,
                "ids_score": 0.55,
                "upr": 0.35,
                "milestone_achieved_rate": 0.75,
                "task_completion_score": 0.78,
                "hallucination_score": 0.85,
                "tool_efficiency_score": 0.82,
                "error_recovery_rate": 1.0,
                "plan_revision_count": 1.0,
                "memory_efficiency_score": 0.72,
            },
            "config": {
                "policy_version": "v1",
                "prompt_version": "v1",
                "model": "test-model",
            },
        },
        {
            "case_id": "test_003",
            "run_tag": "verify",
            "repeat_index": 0,
            "tags": ["error_recovery"],
            "ok": False,
            "latency_ms": 5000.0,
            "tokens_total": 4500,
            "approval_required": False,
            "governance_blocked_count": 0,
            "degraded_count": 2,
            "evidence_missing_steps": ["step_1"],
            # 原有指标
            "ids_score": 0.35,
            "upr": 0.60,
            "milestone_achieved_rate": 0.50,
            # 新增指标 - 这个案例有错误恢复
            "task_completion_score": 0.55,
            "hallucination_score": 0.68,
            "tool_call_success_rate": 0.60,
            "tool_call_count": 5.0,
            "tool_efficiency_score": 0.50,
            "error_recovery_rate": 0.5,  # 部分恢复
            "plan_revision_count": 2.0,
            "memory_usage_rate": 0.50,
            "context_completeness": 0.50,
            "memory_efficiency_score": 0.50,
            "quality": {
                "step_reason_coverage": 0.70,
                "evidence_missing_rate": 0.25,
                "receipt_binding_rate": 0.75,
                "contract_fail_rate": 0.15,
                "explainability_score": 0.65,
                "ids_score": 0.35,
                "upr": 0.60,
                "milestone_achieved_rate": 0.50,
                "task_completion_score": 0.55,
                "hallucination_score": 0.68,
                "tool_efficiency_score": 0.50,
                "error_recovery_rate": 0.5,
                "plan_revision_count": 2.0,
                "memory_efficiency_score": 0.50,
            },
            "config": {
                "policy_version": "v1",
                "prompt_version": "v1",
                "model": "test-model",
            },
        },
    ]


def main():
    print("=" * 80)
    print("RiskMonitor-MultiAgent 新指标验证报告")
    print("=" * 80)

    # 创建模拟记录
    records = create_mock_records()
    print(f"\n模拟记录数: {len(records)}")

    # 汇总指标
    summary = summarize_benchmark_records(records)
    aggregates = summary.get("aggregates", {})

    print("\n" + "-" * 80)
    print("指标汇总结果")
    print("-" * 80)

    # 基础指标
    print(f"\n【基础性能指标】")
    print(f"  - 通过率 (pass_rate):           {summary.get('pass_rate', 0):.2%}")
    print(f"  - 平均延迟 (latency_ms_avg):    {aggregates.get('latency_ms_avg', 0):.2f} ms")
    print(f"  - P95延迟 (latency_ms_p95):     {aggregates.get('latency_ms_p95', 0):.2f} ms")
    print(f"  - 总Token数 (tokens_total):      {aggregates.get('tokens_total', 0)}")

    # 质量解释指标
    print(f"\n【质量与可解释性指标】")
    print(f"  - 步骤理由覆盖率:               {aggregates.get('step_reason_coverage', 0):.2%}")
    print(f"  - 证据缺失率:                    {aggregates.get('evidence_missing_rate', 0):.2%}")
    print(f"  - Receipt绑定率:               {aggregates.get('receipt_binding_rate', 0):.2%}")
    print(f"  - 契约失败率:                    {aggregates.get('contract_fail_rate', 0):.2%}")
    print(f"  - 可解释性评分:                  {aggregates.get('explainability_score', 0):.2%}")

    # 治理安全指标
    print(f"\n【治理与安全指标】")
    print(f"  - 人工审批率:                    {aggregates.get('approval_required_rate', 0):.2%}")
    print(f"  - 治理拦截数:                    {aggregates.get('governance_blocked_avg', 0):.2f}")
    print(f"  - 降级模式触发率:                {aggregates.get('degraded_avg', 0):.2f}")
    print(f"  - 稳定性通过率:                  {aggregates.get('stability_ok_rate', 0):.2%}")

    # 协作过程指标
    print(f"\n【协作与过程指标】")
    print(f"  - 信息多样性 (IDS):              {aggregates.get('ids_avg', 0):.2%}")
    print(f"  - 冗余路径比 (UPR):              {aggregates.get('upr_avg', 0):.2%} (越低越好)")
    print(f"  - 里程碑达成率:                  {aggregates.get('milestone_achieved_rate_avg', 0):.2%}")

    # 新增的 Agent System Metrics
    print(f"\n【新增 Agent System Metrics】")
    print(f"  - 任务完成度评分:                {aggregates.get('task_completion_score_avg', 0):.2%}")
    print(f"  - 幻觉检测评分:                  {aggregates.get('hallucination_score_avg', 0):.2%}")
    print(f"  - 工具调用成功率:                {aggregates.get('tool_call_success_rate_avg', 0):.2%}")
    print(f"  - 平均工具调用次数:              {aggregates.get('tool_call_count_avg', 0):.1f}")
    print(f"  - 工具效率综合得分:              {aggregates.get('tool_efficiency_score_avg', 0):.2%}")
    print(f"  - 错误恢复率:                    {aggregates.get('error_recovery_rate_avg', 0):.2%}")
    print(f"  - Plan修正次数:                  {aggregates.get('plan_revision_count_avg', 0):.2f} (越低越好)")
    print(f"  - 记忆使用比例:                  {aggregates.get('memory_usage_rate_avg', 0):.2%}")
    print(f"  - 上下文完整度:                  {aggregates.get('context_completeness_avg', 0):.2%}")
    print(f"  - 记忆效能综合得分:              {aggregates.get('memory_efficiency_score_avg', 0):.2%}")

    # 门禁检查
    print("\n" + "-" * 80)
    print("质量门禁检查")
    print("-" * 80)

    gate_result = evaluate_quality_gate(summary)

    print(f"\n门禁状态: {'通过' if gate_result.get('passed') else '未通过'}")

    reasons = gate_result.get("reasons", [])
    if reasons:
        print("\n未通过原因:")
        for reason in reasons:
            print(f"  - {reason}")
    else:
        print("\n所有指标均符合阈值要求！")

    print("\n观测值与阈值对比:")
    observed = gate_result.get("observed", {})
    thresholds = gate_result.get("thresholds", {})

    for key, value in observed.items():
        # 找到对应的阈值
        threshold_key = None
        is_min = True
        if key == "step_reason_coverage":
            threshold_key = "min_step_reason_coverage"
        elif key == "evidence_missing_rate":
            threshold_key = "max_evidence_missing_rate"
            is_min = False
        elif key == "receipt_binding_rate":
            threshold_key = "min_receipt_binding_rate"
        elif key == "contract_fail_rate":
            threshold_key = "max_contract_fail_rate"
            is_min = False
        elif key == "latency_ms_p95":
            threshold_key = "max_latency_ms_p95"
            is_min = False
        elif key == "tokens_total":
            threshold_key = "max_tokens_total"
            is_min = False
        elif key == "stability_ok_rate":
            threshold_key = "min_stability_ok_rate"
        elif key == "ids_avg":
            threshold_key = "min_ids_avg"
        elif key == "upr_avg":
            threshold_key = "max_upr_avg"
            is_min = False
        elif key == "milestone_achieved_rate_avg":
            threshold_key = "min_milestone_achieved_rate_avg"
        elif key == "task_completion_score_avg":
            threshold_key = "min_task_completion_score_avg"
        elif key == "hallucination_score_avg":
            threshold_key = "min_hallucination_score_avg"
        elif key == "tool_call_success_rate_avg":
            threshold_key = "min_tool_call_success_rate_avg"
        elif key == "tool_efficiency_score_avg":
            threshold_key = "min_tool_efficiency_score_avg"
        elif key == "error_recovery_rate_avg":
            threshold_key = "min_error_recovery_rate_avg"
        elif key == "plan_revision_count_avg":
            threshold_key = "max_plan_revision_count_avg"
            is_min = False
        elif key == "memory_efficiency_score_avg":
            threshold_key = "min_memory_efficiency_score_avg"

        if threshold_key and threshold_key in thresholds:
            threshold = thresholds[threshold_key]
            status = "✓" if (value >= threshold if is_min else value <= threshold) else "✗"
            cmp_op = ">=" if is_min else "<="
            print(f"  {status} {key}: {value:.4f} {cmp_op} {threshold}")

    print("\n" + "=" * 80)
    print("验证完成!")
    print("=" * 80)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
