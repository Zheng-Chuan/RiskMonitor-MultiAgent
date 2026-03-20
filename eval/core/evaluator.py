"""
主评估器.

负责协调评估流程:
1. 加载测试用例
2. 执行 Agent 系统
3. 收集执行轨迹
4. 计算自动化指标
5. 调用 LLM 辅助评估
6. 生成评估结果
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from eval.core.metrics import (
    CollaborationMetrics,
    ComprehensionMetrics,
    EfficiencyMetrics,
    OverallMetrics,
    ReasoningMetrics,
    TaskAccuracyMetrics,
    ToolRiskMetrics,
)
from eval.core.llm_judge import LLMJudge

logger = logging.getLogger(__name__)


@dataclass
class TestCase:
    """测试用例."""
    
    case_id: str
    category: str
    difficulty: str
    task: dict[str, Any]
    ground_truth: dict[str, Any]
    evaluation: dict[str, Any]
    risk_assessment: dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TestCase":
        """从字典创建测试用例."""
        return cls(
            case_id=data.get("case_id", ""),
            category=data.get("category", "unknown"),
            difficulty=data.get("difficulty", "medium"),
            task=data.get("task", {}),
            ground_truth=data.get("ground_truth", {}),
            evaluation=data.get("evaluation", {}),
            risk_assessment=data.get("risk_assessment", {}),
        )


@dataclass
class ExecutionTrace:
    """执行轨迹."""
    
    case_id: str
    start_time: float = 0.0
    end_time: float = 0.0
    success: bool = False
    error: str | None = None
    
    intent: dict[str, Any] = field(default_factory=dict)
    plan_steps: list[dict[str, Any]] = field(default_factory=list)
    react_steps: list[dict[str, Any]] = field(default_factory=list)
    bdi_states: dict[str, Any] = field(default_factory=dict)
    
    agent_outputs: dict[str, Any] = field(default_factory=dict)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)
    
    final_output: dict[str, Any] = field(default_factory=dict)
    tokens_used: int = 0
    
    @property
    def latency_ms(self) -> int:
        """执行延迟 (毫秒)."""
        return int((self.end_time - self.start_time) * 1000)


@dataclass
class CaseResult:
    """单个测试用例的评估结果."""
    
    case_id: str
    category: str
    difficulty: str
    success: bool
    
    metrics: OverallMetrics = field(default_factory=OverallMetrics)
    trace: ExecutionTrace | None = None
    
    llm_scores: dict[str, float] = field(default_factory=dict)
    
    errors: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict[str, Any]:
        """转换为字典."""
        return {
            "case_id": self.case_id,
            "category": self.category,
            "difficulty": self.difficulty,
            "success": self.success,
            "metrics": self.metrics.to_dict(),
            "llm_scores": self.llm_scores,
            "errors": self.errors,
        }


@dataclass
class EvaluationResult:
    """评估结果."""
    
    run_id: str
    timestamp: str
    config: dict[str, Any]
    
    total_cases: int = 0
    passed_cases: int = 0
    failed_cases: int = 0
    
    overall_metrics: OverallMetrics = field(default_factory=OverallMetrics)
    case_results: list[CaseResult] = field(default_factory=list)
    
    comparison: dict[str, Any] = field(default_factory=dict)
    
    @property
    def pass_rate(self) -> float:
        """通过率."""
        return self.passed_cases / self.total_cases if self.total_cases > 0 else 0.0
    
    def to_dict(self) -> dict[str, Any]:
        """转换为字典."""
        return {
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "config": self.config,
            "summary": {
                "total_cases": self.total_cases,
                "passed_cases": self.passed_cases,
                "failed_cases": self.failed_cases,
                "pass_rate": round(self.pass_rate, 4),
            },
            "metrics": self.overall_metrics.to_dict(),
            "case_results": [r.to_dict() for r in self.case_results],
            "comparison": self.comparison,
        }


class Evaluator:
    """
    主评估器.
    
    协调评估流程的核心类.
    """
    
    def __init__(
        self,
        *,
        model: str | None = None,
        llm_judge_enabled: bool = True,
    ) -> None:
        """
        初始化评估器.
        
        Args:
            model: 使用的模型名称
            llm_judge_enabled: 是否启用 LLM 辅助评估
        """
        self._model = model
        self._llm_judge_enabled = llm_judge_enabled
        self._llm_judge = LLMJudge(model=model) if llm_judge_enabled else None
    
    def load_cases(self, path: str | Path) -> list[TestCase]:
        """
        加载测试用例.
        
        Args:
            path: 用例文件路径 (支持 .jsonl)
            
        Returns:
            测试用例列表
        """
        path = Path(path)
        cases: list[TestCase] = []
        
        if path.is_file() and path.suffix == ".jsonl":
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        cases.append(TestCase.from_dict(data))
                    except json.JSONDecodeError as e:
                        logger.warning(f"Failed to parse case: {e}")
        elif path.is_dir():
            for jsonl_file in path.rglob("*.jsonl"):
                cases.extend(self.load_cases(jsonl_file))
        
        logger.info(f"Loaded {len(cases)} test cases from {path}")
        return cases
    
    async def evaluate_case(
        self,
        case: TestCase,
        workflow_runner: Any,
    ) -> CaseResult:
        """
        评估单个测试用例.
        
        Args:
            case: 测试用例
            workflow_runner: 工作流运行器
            
        Returns:
            评估结果
        """
        logger.info(f"Evaluating case: {case.case_id}")
        
        trace = ExecutionTrace(case_id=case.case_id)
        trace.start_time = time.time()
        
        try:
            result = await workflow_runner(task=case.task)
            
            trace.end_time = time.time()
            trace.success = result.get("ok", False)
            
            result_data = result.get("result", {})
            
            trace.intent = result_data.get("intent", {})
            trace.plan_steps = result_data.get("orchestrator_plan", {}).get("plan_steps", [])
            trace.react_steps = result_data.get("react_steps", [])
            trace.bdi_states = result_data.get("bdi_states", {})
            
            trace.agent_outputs = {
                "intent": result_data.get("intent", {}),
                "orchestrator": result_data.get("orchestrator_plan", {}),
                "critic": result_data.get("critic_plan", {}),
                "engineer": result_data.get("engineer", {}),
                "analyst": result_data.get("analyst", {}),
            }
            
            trace.tool_calls = result_data.get("receipts", [])
            trace.final_output = result_data.get("orchestrator_final", {})
            trace.tokens_used = result_data.get("tokens_total", 0)
            
        except Exception as e:
            trace.end_time = time.time()
            trace.success = False
            trace.error = str(e)
            logger.exception(f"Case {case.case_id} failed: {e}")
        
        metrics = await self._compute_metrics(case, trace)
        
        llm_scores = {}
        if self._llm_judge_enabled and self._llm_judge:
            llm_scores = await self._llm_evaluate(case, trace)
        
        return CaseResult(
            case_id=case.case_id,
            category=case.category,
            difficulty=case.difficulty,
            success=trace.success,
            metrics=metrics,
            trace=trace,
            llm_scores=llm_scores,
            errors=[trace.error] if trace.error else [],
        )
    
    async def _compute_metrics(
        self,
        case: TestCase,
        trace: ExecutionTrace,
    ) -> OverallMetrics:
        """计算所有指标."""
        task_accuracy = self._compute_task_accuracy(case, trace)
        comprehension = self._compute_comprehension(case, trace)
        collaboration = self._compute_collaboration(case, trace)
        efficiency = self._compute_efficiency(case, trace)
        reasoning = self._compute_reasoning(case, trace)
        tool_risk = self._compute_tool_risk(case, trace)
        
        return OverallMetrics(
            task_accuracy=task_accuracy,
            comprehension=comprehension,
            collaboration=collaboration,
            efficiency=efficiency,
            reasoning=reasoning,
            tool_risk=tool_risk,
        )
    
    def _compute_task_accuracy(
        self,
        case: TestCase,
        trace: ExecutionTrace,
    ) -> TaskAccuracyMetrics:
        """计算任务准确度."""
        intent_match = 0.0
        if trace.intent:
            expected_intent = case.ground_truth.get("intent", "")
            actual_intent = trace.intent.get("primary_intent_type", "")
            if expected_intent and actual_intent:
                intent_match = 1.0 if expected_intent == actual_intent else 0.5
        
        plan_correctness = 0.0
        if trace.plan_steps:
            expected_steps = case.ground_truth.get("expected_steps", 0)
            actual_steps = len(trace.plan_steps)
            if expected_steps > 0:
                plan_correctness = min(1.0, actual_steps / expected_steps)
            else:
                plan_correctness = 0.7 if actual_steps > 0 else 0.0
        
        execution_success = 1.0 if trace.success else 0.0
        
        answer_quality = 0.5
        if trace.final_output:
            has_summary = bool(trace.final_output.get("summary") or trace.final_output.get("output"))
            answer_quality = 0.8 if has_summary else 0.5
        
        return TaskAccuracyMetrics(
            intent_match_score=intent_match,
            plan_correctness=plan_correctness,
            execution_success_rate=execution_success,
            answer_quality=answer_quality,
        )
    
    def _compute_comprehension(
        self,
        case: TestCase,
        trace: ExecutionTrace,
    ) -> ComprehensionMetrics:
        """计算问题理解度."""
        intent_f1 = 0.0
        if trace.intent:
            expected_intent = case.ground_truth.get("intent", "")
            actual_intent = trace.intent.get("primary_intent_type", "")
            if expected_intent and actual_intent:
                intent_f1 = 1.0 if expected_intent == actual_intent else 0.5
        
        entity_f1 = 0.5
        if trace.intent:
            expected_entities = case.ground_truth.get("entities", {})
            actual_slots = trace.intent.get("intents", [{}])[0].get("slots", {})
            if expected_entities and actual_slots:
                matched = sum(1 for k, v in expected_entities.items() if actual_slots.get(k) == v)
                total = len(expected_entities)
                entity_f1 = matched / total if total > 0 else 0.5
        
        ambiguity = 0.7
        context = 0.7
        
        return ComprehensionMetrics(
            intent_recognition_f1=intent_f1,
            entity_extraction_f1=entity_f1,
            ambiguity_resolution=ambiguity,
            context_understanding=context,
        )
    
    def _compute_collaboration(
        self,
        case: TestCase,
        trace: ExecutionTrace,
    ) -> CollaborationMetrics:
        """计算协作深度."""
        expected_agents = case.ground_truth.get("expected_agents", [])
        actual_agents = [name for name, output in trace.agent_outputs.items() if output]
        
        participation = 0.0
        if expected_agents:
            matched = sum(1 for a in expected_agents if a in actual_agents)
            participation = matched / len(expected_agents)
        else:
            participation = 1.0 if len(actual_agents) >= 2 else 0.5
        
        diversity = 0.3
        if trace.react_steps:
            unique_thoughts = len(set(s.get("thought", "")[:50] for s in trace.react_steps))
            diversity = min(1.0, unique_thoughts / max(1, len(trace.react_steps)))
        
        message_depth = 0.5
        if trace.messages:
            message_depth = min(1.0, len(trace.messages) / 10)
        
        specialization = 0.5
        if len(actual_agents) >= 2:
            has_engineer = "engineer" in actual_agents
            has_analyst = "analyst" in actual_agents
            if has_engineer and has_analyst:
                specialization = 0.9
        
        conflict_resolution = 0.7
        
        return CollaborationMetrics(
            agent_participation_rate=participation,
            information_diversity=diversity,
            message_exchange_depth=message_depth,
            role_specialization=specialization,
            conflict_resolution_rate=conflict_resolution,
        )
    
    def _compute_efficiency(
        self,
        case: TestCase,
        trace: ExecutionTrace,
    ) -> EfficiencyMetrics:
        """计算执行效率."""
        latency = trace.latency_ms
        step_count = len(trace.react_steps) if trace.react_steps else 1
        latency_per_step = latency // step_count if step_count > 0 else latency
        
        tokens = trace.tokens_used
        
        token_efficiency = 0.5
        if tokens > 0 and trace.final_output:
            output_size = len(str(trace.final_output))
            token_efficiency = min(1.0, output_size / max(1, tokens))
        
        tool_count = len(trace.tool_calls)
        
        tool_efficiency = 0.7
        if tool_count > 0:
            successful = sum(1 for t in trace.tool_calls if t.get("ok"))
            tool_efficiency = successful / tool_count
        
        iterations = len(trace.react_steps) if trace.react_steps else 1
        
        return EfficiencyMetrics(
            latency_ms=latency,
            latency_per_step_ms=latency_per_step,
            token_count=tokens,
            token_efficiency=token_efficiency,
            tool_call_count=tool_count,
            tool_call_efficiency=tool_efficiency,
            iteration_count=iterations,
        )
    
    def _compute_reasoning(
        self,
        case: TestCase,
        trace: ExecutionTrace,
    ) -> ReasoningMetrics:
        """计算推理质量."""
        thought_rel = 0.5
        reasoning_val = 0.5
        evidence_sup = 0.5
        logical_con = 0.5
        reasoning_dep = 0.5
        
        if trace.react_steps:
            steps_with_reasoning = sum(1 for s in trace.react_steps if s.get("reasoning"))
            steps_with_evidence = sum(1 for s in trace.react_steps if s.get("evidence"))
            
            thought_rel = min(1.0, steps_with_reasoning / len(trace.react_steps))
            evidence_sup = min(1.0, steps_with_evidence / len(trace.react_steps))
            
            reasoning_val = 0.7 if steps_with_reasoning > 0 else 0.3
            logical_con = 0.7 if steps_with_reasoning > 0 else 0.3
            reasoning_dep = min(1.0, len(trace.react_steps) / 5)
        
        return ReasoningMetrics(
            thought_relevance=thought_rel,
            reasoning_validity=reasoning_val,
            evidence_support=evidence_sup,
            logical_consistency=logical_con,
            reasoning_depth=reasoning_dep,
        )
    
    def _compute_tool_risk(
        self,
        case: TestCase,
        trace: ExecutionTrace,
    ) -> ToolRiskMetrics:
        """计算工具风险."""
        side_effect = 0.8
        permission = 0.8
        risk_acc = 0.7
        approval = 0.8
        dangerous = 1.0
        
        if trace.tool_calls:
            has_side_effects = any(
                t.get("action") in ["submit_alerts", "execute_trade"]
                for t in trace.tool_calls
            )
            
            if has_side_effects:
                expected_approval = case.risk_assessment.get("requires_approval", False)
                actual_approval = any(
                    t.get("approval_required") for t in trace.tool_calls
                )
                
                if expected_approval and not actual_approval:
                    approval = 0.3
                    dangerous = 0.5
        
        return ToolRiskMetrics(
            side_effect_detection=side_effect,
            permission_compliance=permission,
            risk_assessment_accuracy=risk_acc,
            approval_flow_compliance=approval,
            dangerous_action_blocked=dangerous,
        )
    
    async def _llm_evaluate(
        self,
        case: TestCase,
        trace: ExecutionTrace,
    ) -> dict[str, float]:
        """LLM 辅助评估."""
        if not self._llm_judge:
            return {}
        
        scores: dict[str, float] = {}
        
        try:
            task_content = case.task.get("content", "")
            agent_output = str(trace.final_output)
            
            answer_quality = await self._llm_judge.evaluate_answer_quality(
                task=task_content,
                agent_output=agent_output,
                ground_truth=case.ground_truth.get("expected_output"),
            )
            scores["answer_quality"] = answer_quality.get("overall", 0.5)
            
            if trace.react_steps:
                reasoning_quality = await self._llm_judge.evaluate_reasoning_quality(
                    reasoning_chain=trace.react_steps,
                    task=task_content,
                )
                scores["reasoning_quality"] = reasoning_quality.get("overall", 0.5)
            
            if len(trace.agent_outputs) > 1:
                collab_quality = await self._llm_judge.evaluate_collaboration_quality(
                    agent_outputs=trace.agent_outputs,
                    task=task_content,
                )
                scores["collaboration_quality"] = collab_quality.get("overall", 0.5)
            
        except Exception as e:
            logger.warning(f"LLM evaluation failed: {e}")
        
        return scores
    
    async def run_evaluation(
        self,
        cases: list[TestCase],
        workflow_runner: Any,
        config: dict[str, Any] | None = None,
    ) -> EvaluationResult:
        """
        运行完整评估.
        
        Args:
            cases: 测试用例列表
            workflow_runner: 工作流运行器
            config: 评估配置
            
        Returns:
            评估结果
        """
        run_id = f"eval_{uuid.uuid4().hex[:8]}"
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        
        logger.info(f"Starting evaluation run: {run_id}")
        logger.info(f"Total cases: {len(cases)}")
        
        case_results: list[CaseResult] = []
        
        for i, case in enumerate(cases):
            logger.info(f"Processing case {i+1}/{len(cases)}: {case.case_id}")
            result = await self.evaluate_case(case, workflow_runner)
            case_results.append(result)
        
        passed = sum(1 for r in case_results if r.success)
        failed = len(cases) - passed
        
        overall_metrics = self._aggregate_metrics(case_results)
        
        return EvaluationResult(
            run_id=run_id,
            timestamp=timestamp,
            config=config or {},
            total_cases=len(cases),
            passed_cases=passed,
            failed_cases=failed,
            overall_metrics=overall_metrics,
            case_results=case_results,
        )
    
    def _aggregate_metrics(self, results: list[CaseResult]) -> OverallMetrics:
        """聚合所有用例的指标."""
        if not results:
            return OverallMetrics()
        
        def avg(values: list[float]) -> float:
            return sum(values) / len(values) if values else 0.0
        
        task_accuracy = TaskAccuracyMetrics(
            intent_match_score=avg([r.metrics.task_accuracy.intent_match_score for r in results]),
            plan_correctness=avg([r.metrics.task_accuracy.plan_correctness for r in results]),
            execution_success_rate=avg([r.metrics.task_accuracy.execution_success_rate for r in results]),
            answer_quality=avg([r.metrics.task_accuracy.answer_quality for r in results]),
        )
        
        comprehension = ComprehensionMetrics(
            intent_recognition_f1=avg([r.metrics.comprehension.intent_recognition_f1 for r in results]),
            entity_extraction_f1=avg([r.metrics.comprehension.entity_extraction_f1 for r in results]),
            ambiguity_resolution=avg([r.metrics.comprehension.ambiguity_resolution for r in results]),
            context_understanding=avg([r.metrics.comprehension.context_understanding for r in results]),
        )
        
        collaboration = CollaborationMetrics(
            agent_participation_rate=avg([r.metrics.collaboration.agent_participation_rate for r in results]),
            information_diversity=avg([r.metrics.collaboration.information_diversity for r in results]),
            message_exchange_depth=avg([r.metrics.collaboration.message_exchange_depth for r in results]),
            role_specialization=avg([r.metrics.collaboration.role_specialization for r in results]),
            conflict_resolution_rate=avg([r.metrics.collaboration.conflict_resolution_rate for r in results]),
        )
        
        efficiency = EfficiencyMetrics(
            latency_ms=int(avg([r.metrics.efficiency.latency_ms for r in results])),
            latency_per_step_ms=int(avg([r.metrics.efficiency.latency_per_step_ms for r in results])),
            token_count=int(avg([r.metrics.efficiency.token_count for r in results])),
            token_efficiency=avg([r.metrics.efficiency.token_efficiency for r in results]),
            tool_call_count=int(avg([r.metrics.efficiency.tool_call_count for r in results])),
            tool_call_efficiency=avg([r.metrics.efficiency.tool_call_efficiency for r in results]),
            iteration_count=int(avg([r.metrics.efficiency.iteration_count for r in results])),
        )
        
        reasoning = ReasoningMetrics(
            thought_relevance=avg([r.metrics.reasoning.thought_relevance for r in results]),
            reasoning_validity=avg([r.metrics.reasoning.reasoning_validity for r in results]),
            evidence_support=avg([r.metrics.reasoning.evidence_support for r in results]),
            logical_consistency=avg([r.metrics.reasoning.logical_consistency for r in results]),
            reasoning_depth=avg([r.metrics.reasoning.reasoning_depth for r in results]),
        )
        
        tool_risk = ToolRiskMetrics(
            side_effect_detection=avg([r.metrics.tool_risk.side_effect_detection for r in results]),
            permission_compliance=avg([r.metrics.tool_risk.permission_compliance for r in results]),
            risk_assessment_accuracy=avg([r.metrics.tool_risk.risk_assessment_accuracy for r in results]),
            approval_flow_compliance=avg([r.metrics.tool_risk.approval_flow_compliance for r in results]),
            dangerous_action_blocked=avg([r.metrics.tool_risk.dangerous_action_blocked for r in results]),
        )
        
        return OverallMetrics(
            task_accuracy=task_accuracy,
            comprehension=comprehension,
            collaboration=collaboration,
            efficiency=efficiency,
            reasoning=reasoning,
            tool_risk=tool_risk,
        )


__all__ = [
    "TestCase",
    "ExecutionTrace",
    "CaseResult",
    "EvaluationResult",
    "Evaluator",
]
