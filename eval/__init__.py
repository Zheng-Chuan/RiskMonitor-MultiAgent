"""
评估模块 - 多 Agent 系统评估框架.

基于学术界和工业界最佳实践，提供全面的多 Agent 系统评估能力.

核心特性:
1. 多维度评估: 任务准确度、问题理解度、协作深度、执行效率、推理质量、工具风险
2. 自动化 + LLM 辅助评估: 客观指标自动计算，主观指标用 LLM 评估
3. 历史对比: 与上次评估结果对比
4. 业界基准对比: 与 GAIA、MultiAgentBench、PlanBench 等对比
"""

from eval.core.evaluator import EvaluationResult, Evaluator
from eval.core.metrics import (
    TaskAccuracyMetrics,
    ComprehensionMetrics,
    CollaborationMetrics,
    EfficiencyMetrics,
    ReasoningMetrics,
    ToolRiskMetrics,
)
from eval.core.llm_judge import LLMJudge
from eval.core.report import ReportGenerator

__all__ = [
    "Evaluator",
    "EvaluationResult",
    "TaskAccuracyMetrics",
    "ComprehensionMetrics",
    "CollaborationMetrics",
    "EfficiencyMetrics",
    "ReasoningMetrics",
    "ToolRiskMetrics",
    "LLMJudge",
    "ReportGenerator",
]
