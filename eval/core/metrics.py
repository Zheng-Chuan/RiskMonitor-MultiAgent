"""
评估指标定义.

基于学术界和工业界最佳实践:
- GAIA: General AI Assistant Benchmark
- MultiAgentBench: Multi-Agent Collaboration Benchmark
- PlanBench: Planning and Execution Benchmark
- GEMMAS: Graph-based Evaluation Metrics for Multi-Agent Systems

六大评估维度:
1. 任务准确度 (Task Accuracy)
2. 问题理解度 (Comprehension)
3. 协作深度 (Collaboration)
4. 执行效率 (Efficiency)
5. 推理质量 (Reasoning)
6. 工具风险 (Tool Risk)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TaskAccuracyMetrics:
    """
    任务准确度指标.
    
    基于 GAIA 和 PlanBench 学术基准.
    
    Attributes:
        intent_match_score: 意图匹配度 (0-1)
        plan_correctness: 计划正确性 (0-1)
        execution_success_rate: 执行成功率 (0-1)
        answer_quality: 答案质量 (LLM 评估, 0-1)
    """
    
    intent_match_score: float = 0.0
    plan_correctness: float = 0.0
    execution_success_rate: float = 0.0
    answer_quality: float = 0.0
    
    @property
    def overall_accuracy(self) -> float:
        """综合准确度."""
        weights = [0.25, 0.25, 0.25, 0.25]
        values = [
            self.intent_match_score,
            self.plan_correctness,
            self.execution_success_rate,
            self.answer_quality,
        ]
        return sum(w * v for w, v in zip(weights, values))
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "intent_match_score": round(self.intent_match_score, 4),
            "plan_correctness": round(self.plan_correctness, 4),
            "execution_success_rate": round(self.execution_success_rate, 4),
            "answer_quality": round(self.answer_quality, 4),
            "overall_accuracy": round(self.overall_accuracy, 4),
        }


@dataclass
class ComprehensionMetrics:
    """
    问题理解度指标.
    
    Attributes:
        intent_recognition_f1: 意图识别 F1 (0-1)
        entity_extraction_f1: 实体提取 F1 (0-1)
        ambiguity_resolution: 歧义消解能力 (LLM 评估, 0-1)
        context_understanding: 上下文理解 (LLM 评估, 0-1)
    """
    
    intent_recognition_f1: float = 0.0
    entity_extraction_f1: float = 0.0
    ambiguity_resolution: float = 0.0
    context_understanding: float = 0.0
    
    @property
    def overall_comprehension(self) -> float:
        """综合理解度."""
        weights = [0.3, 0.25, 0.25, 0.2]
        values = [
            self.intent_recognition_f1,
            self.entity_extraction_f1,
            self.ambiguity_resolution,
            self.context_understanding,
        ]
        return sum(w * v for w, v in zip(weights, values))
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "intent_recognition_f1": round(self.intent_recognition_f1, 4),
            "entity_extraction_f1": round(self.entity_extraction_f1, 4),
            "ambiguity_resolution": round(self.ambiguity_resolution, 4),
            "context_understanding": round(self.context_understanding, 4),
            "overall_comprehension": round(self.overall_comprehension, 4),
        }


@dataclass
class CollaborationMetrics:
    """
    协作深度指标.
    
    基于 MultiAgentBench 和 GEMMAS 学术基准.
    
    Attributes:
        agent_participation_rate: Agent 参与率 (0-1)
        information_diversity: 信息多样性 IDS (0-1)
        message_exchange_depth: 消息交换深度 (0-1)
        role_specialization: 角色专业化程度 (0-1)
        conflict_resolution_rate: 冲突解决率 (0-1)
    """
    
    agent_participation_rate: float = 0.0
    information_diversity: float = 0.0
    message_exchange_depth: float = 0.0
    role_specialization: float = 0.0
    conflict_resolution_rate: float = 0.0
    
    @property
    def overall_collaboration(self) -> float:
        """综合协作度."""
        weights = [0.25, 0.25, 0.2, 0.15, 0.15]
        values = [
            self.agent_participation_rate,
            self.information_diversity,
            self.message_exchange_depth,
            self.role_specialization,
            self.conflict_resolution_rate,
        ]
        return sum(w * v for w, v in zip(weights, values))
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_participation_rate": round(self.agent_participation_rate, 4),
            "information_diversity": round(self.information_diversity, 4),
            "message_exchange_depth": round(self.message_exchange_depth, 4),
            "role_specialization": round(self.role_specialization, 4),
            "conflict_resolution_rate": round(self.conflict_resolution_rate, 4),
            "overall_collaboration": round(self.overall_collaboration, 4),
        }


@dataclass
class EfficiencyMetrics:
    """
    执行效率指标.
    
    Attributes:
        latency_ms: 总延迟 (毫秒)
        latency_per_step_ms: 每步平均延迟 (毫秒)
        token_count: Token 消耗
        token_efficiency: Token 效率 (输出价值/Token)
        tool_call_count: 工具调用次数
        tool_call_efficiency: 工具调用效率 (0-1)
        iteration_count: 迭代次数
    """
    
    latency_ms: int = 0
    latency_per_step_ms: int = 0
    token_count: int = 0
    token_efficiency: float = 0.0
    tool_call_count: int = 0
    tool_call_efficiency: float = 0.0
    iteration_count: int = 0
    
    @property
    def overall_efficiency(self) -> float:
        """综合效率评分 (0-1)."""
        latency_score = max(0, 1 - (self.latency_ms / 60000))
        token_score = max(0, 1 - (self.token_count / 100000))
        tool_score = self.tool_call_efficiency
        
        return (latency_score * 0.3 + token_score * 0.3 + tool_score * 0.4)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "latency_ms": self.latency_ms,
            "latency_per_step_ms": self.latency_per_step_ms,
            "token_count": self.token_count,
            "token_efficiency": round(self.token_efficiency, 4),
            "tool_call_count": self.tool_call_count,
            "tool_call_efficiency": round(self.tool_call_efficiency, 4),
            "iteration_count": self.iteration_count,
            "overall_efficiency": round(self.overall_efficiency, 4),
        }


@dataclass
class ReasoningMetrics:
    """
    推理质量指标.
    
    基于 CoT (Chain-of-Thought) Benchmarks.
    
    Attributes:
        thought_relevance: 思考相关性 (LLM 评估, 0-1)
        reasoning_validity: 推理有效性 (LLM 评估, 0-1)
        evidence_support: 证据支撑度 (0-1)
        logical_consistency: 逻辑一致性 (LLM 评估, 0-1)
        reasoning_depth: 推理深度 (LLM 评估, 0-1)
    """
    
    thought_relevance: float = 0.0
    reasoning_validity: float = 0.0
    evidence_support: float = 0.0
    logical_consistency: float = 0.0
    reasoning_depth: float = 0.0
    
    @property
    def overall_reasoning(self) -> float:
        """综合推理质量."""
        weights = [0.2, 0.25, 0.2, 0.2, 0.15]
        values = [
            self.thought_relevance,
            self.reasoning_validity,
            self.evidence_support,
            self.logical_consistency,
            self.reasoning_depth,
        ]
        return sum(w * v for w, v in zip(weights, values))
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "thought_relevance": round(self.thought_relevance, 4),
            "reasoning_validity": round(self.reasoning_validity, 4),
            "evidence_support": round(self.evidence_support, 4),
            "logical_consistency": round(self.logical_consistency, 4),
            "reasoning_depth": round(self.reasoning_depth, 4),
            "overall_reasoning": round(self.overall_reasoning, 4),
        }


@dataclass
class ToolRiskMetrics:
    """
    工具风险指标.
    
    Attributes:
        side_effect_detection: 副作用检测率 (0-1)
        permission_compliance: 权限合规率 (0-1)
        risk_assessment_accuracy: 风险评估准确率 (LLM 评估, 0-1)
        approval_flow_compliance: 审批流程合规率 (0-1)
        dangerous_action_blocked: 危险动作拦截率 (0-1)
    """
    
    side_effect_detection: float = 0.0
    permission_compliance: float = 0.0
    risk_assessment_accuracy: float = 0.0
    approval_flow_compliance: float = 0.0
    dangerous_action_blocked: float = 0.0
    
    @property
    def overall_safety(self) -> float:
        """综合安全性."""
        weights = [0.2, 0.2, 0.2, 0.2, 0.2]
        values = [
            self.side_effect_detection,
            self.permission_compliance,
            self.risk_assessment_accuracy,
            self.approval_flow_compliance,
            self.dangerous_action_blocked,
        ]
        return sum(w * v for w, v in zip(weights, values))
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "side_effect_detection": round(self.side_effect_detection, 4),
            "permission_compliance": round(self.permission_compliance, 4),
            "risk_assessment_accuracy": round(self.risk_assessment_accuracy, 4),
            "approval_flow_compliance": round(self.approval_flow_compliance, 4),
            "dangerous_action_blocked": round(self.dangerous_action_blocked, 4),
            "overall_safety": round(self.overall_safety, 4),
        }


@dataclass
class OverallMetrics:
    """
    综合评估指标.
    
    汇总六大维度的评估结果.
    """
    
    task_accuracy: TaskAccuracyMetrics = field(default_factory=TaskAccuracyMetrics)
    comprehension: ComprehensionMetrics = field(default_factory=ComprehensionMetrics)
    collaboration: CollaborationMetrics = field(default_factory=CollaborationMetrics)
    efficiency: EfficiencyMetrics = field(default_factory=EfficiencyMetrics)
    reasoning: ReasoningMetrics = field(default_factory=ReasoningMetrics)
    tool_risk: ToolRiskMetrics = field(default_factory=ToolRiskMetrics)
    
    @property
    def overall_score(self) -> float:
        """综合评分 (0-1)."""
        weights = [0.25, 0.15, 0.2, 0.15, 0.15, 0.1]
        values = [
            self.task_accuracy.overall_accuracy,
            self.comprehension.overall_comprehension,
            self.collaboration.overall_collaboration,
            self.efficiency.overall_efficiency,
            self.reasoning.overall_reasoning,
            self.tool_risk.overall_safety,
        ]
        return sum(w * v for w, v in zip(weights, values))
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "task_accuracy": self.task_accuracy.to_dict(),
            "comprehension": self.comprehension.to_dict(),
            "collaboration": self.collaboration.to_dict(),
            "efficiency": self.efficiency.to_dict(),
            "reasoning": self.reasoning.to_dict(),
            "tool_risk": self.tool_risk.to_dict(),
            "overall_score": round(self.overall_score, 4),
        }


__all__ = [
    "TaskAccuracyMetrics",
    "ComprehensionMetrics",
    "CollaborationMetrics",
    "EfficiencyMetrics",
    "ReasoningMetrics",
    "ToolRiskMetrics",
    "OverallMetrics",
]
