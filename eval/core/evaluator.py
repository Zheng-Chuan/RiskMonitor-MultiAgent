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
    
    llm_interactions: list[dict[str, Any]] = field(default_factory=list)
    
    @property
    def latency_ms(self) -> int:
        """执行延迟 (毫秒)."""
        return int((self.end_time - self.start_time) * 1000)
    
    def to_dict(self) -> dict[str, Any]:
        """转换为字典."""
        return {
            "case_id": self.case_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "latency_ms": self.latency_ms,
            "success": self.success,
            "error": self.error,
            "intent": self.intent,
            "plan_steps": self.plan_steps,
            "react_steps": self.react_steps,
            "bdi_states": self.bdi_states,
            "agent_outputs": self.agent_outputs,
            "tool_calls": self.tool_calls,
            "messages": self.messages,
            "final_output": self.final_output,
            "tokens_used": self.tokens_used,
            "llm_interactions": self.llm_interactions,
        }


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
        result = {
            "case_id": self.case_id,
            "category": self.category,
            "difficulty": self.difficulty,
            "success": self.success,
            "metrics": self.metrics.to_dict(),
            "llm_scores": self.llm_scores,
            "errors": self.errors,
        }
        if self.trace is not None:
            result["trace"] = self.trace.to_dict()
        return result


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
            
            if "result" in result_data:
                result_data = result_data.get("result", {})

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
            trace.llm_interactions = result_data.get("llm_interactions", [])

        except Exception as e:
            trace.end_time = time.time()
            trace.success = False
            trace.error = str(e)
            logger.exception(f"Case {case.case_id} failed: {e}")

        # 先执行 LLM 评估,获取详细分数
        llm_scores = {}
        if self._llm_judge_enabled and self._llm_judge:
            llm_scores = await self._llm_evaluate(case, trace)

        # 使用 LLM 评估结果计算指标
        metrics = await self._compute_metrics(case, trace, llm_scores)

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
        llm_scores: dict[str, Any],
    ) -> OverallMetrics:
        """计算所有指标."""
        task_accuracy = self._compute_task_accuracy(case, trace, llm_scores)
        comprehension = self._compute_comprehension(case, trace, llm_scores)
        collaboration = self._compute_collaboration(case, trace, llm_scores)
        efficiency = self._compute_efficiency(case, trace)
        reasoning = self._compute_reasoning(case, trace, llm_scores)
        tool_risk = self._compute_tool_risk(case, trace, llm_scores)

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
        llm_scores: dict[str, Any],
    ) -> TaskAccuracyMetrics:
        """计算任务准确度."""
        # intent_match: 优先使用 LLMJudge 评估,否则使用启发式
        intent_match = llm_scores.get("intent_match", {}).get("score")
        if intent_match is None or intent_match == 0.0:
            if trace.intent:
                expected_intent = case.ground_truth.get("intent", "")
                actual_intent = trace.intent.get("primary_intent_type", "")
                if expected_intent and actual_intent:
                    intent_match = 1.0 if expected_intent == actual_intent else 0.5
                elif actual_intent:
                    intent_match = 0.7
            else:
                intent_match = 0.0

        # answer_quality: 优先使用 LLMJudge 评估,否则使用启发式
        answer_quality = llm_scores.get("answer_quality", {}).get("overall")
        if answer_quality is None or answer_quality == 0.0:
            if trace.success:
                if trace.react_steps:
                    answer_quality = 0.7
                elif trace.intent:
                    answer_quality = 0.6
                else:
                    answer_quality = 0.5
            else:
                answer_quality = 0.3

        # plan_correctness: 启发式计算 (步数合理性)
        plan_correctness = 0.0
        if trace.plan_steps:
            expected_steps = case.ground_truth.get("expected_steps", 0)
            actual_steps = len(trace.plan_steps)
            if expected_steps > 0:
                plan_correctness = min(1.0, actual_steps / expected_steps)
            else:
                plan_correctness = 0.7 if actual_steps > 0 else 0.0
        elif trace.react_steps:
            # 如果没有 plan_steps 但有 react_steps,给一个合理的分数
            plan_correctness = 0.6
        elif trace.success:
            # 如果执行成功,即使没有计划步骤也给基础分
            plan_correctness = 0.4

        # execution_success: 执行是否成功
        execution_success = 1.0 if trace.success else 0.0

        return TaskAccuracyMetrics(
            intent_match_score=float(intent_match),
            plan_correctness=float(plan_correctness),
            execution_success_rate=float(execution_success),
            answer_quality=float(answer_quality),
        )
    
    def _compute_comprehension(
        self,
        case: TestCase,
        trace: ExecutionTrace,
        llm_scores: dict[str, Any],
    ) -> ComprehensionMetrics:
        """计算问题理解度."""
        # intent_recognition_f1: 意图识别 F1 (启发式,基于 slots 匹配)
        entity_f1 = 0.5
        if trace.intent:
            expected_entities = case.ground_truth.get("entities", {})
            actual_slots = trace.intent.get("intents", [{}])[0].get("slots", {})
            if expected_entities and actual_slots:
                matched = sum(1 for k, v in expected_entities.items() if actual_slots.get(k) == v)
                total = len(expected_entities)
                precision = matched / len(actual_slots) if actual_slots else 0.0
                recall = matched / total if total > 0 else 0.0
                # 计算真正的 F1 分数
                if precision + recall > 0:
                    entity_f1 = 2 * (precision * recall) / (precision + recall)
                else:
                    entity_f1 = 0.0
            elif actual_slots:
                entity_f1 = 0.6

        # intent_match_score: 意图匹配度 (LLMJudge 评估语义相似度)
        intent_match = llm_scores.get("intent_match", {}).get("score")
        if intent_match is None or intent_match == 0.0:
            # fallback: 启发式
            if trace.intent:
                expected_intent = case.ground_truth.get("intent", "")
                actual_intent = trace.intent.get("primary_intent_type", "")
                if expected_intent and actual_intent:
                    intent_match = 1.0 if expected_intent == actual_intent else 0.5
                elif actual_intent:
                    intent_match = 0.7
            else:
                intent_match = 0.0

        # ambiguity_resolution: 歧义消解 (LLMJudge)
        ambiguity_score = llm_scores.get("ambiguity_resolution", {}).get("score")
        if ambiguity_score is None:
            ambiguity_score = 0.7  # fallback

        # context_understanding: 上下文理解 (LLMJudge)
        context_score = llm_scores.get("context_understanding", {}).get("score")
        if context_score is None or context_score == 0.0:
            # fallback: 启发式 - 检查是否有意图识别和反应步骤
            if trace.intent and trace.react_steps:
                context_score = 0.75
            elif trace.intent:
                context_score = 0.6
            elif trace.success:
                context_score = 0.5
            else:
                context_score = 0.3

        return ComprehensionMetrics(
            intent_recognition_f1=float(entity_f1),  # 真正的 F1 分数
            entity_extraction_f1=float(entity_f1),  # 复用 entity_f1
            ambiguity_resolution=float(ambiguity_score),
            context_understanding=float(context_score),
        )
    
    def _compute_collaboration(
        self,
        case: TestCase,
        trace: ExecutionTrace,
        llm_scores: dict[str, Any],
    ) -> CollaborationMetrics:
        """计算协作深度."""
        expected_agents = case.ground_truth.get("expected_agents", [])
        # 改进:只要有数据就认为 agent 参与了,不要求是非空字典
        actual_agents = [name for name, output in trace.agent_outputs.items() if output is not None]

        # agent_participation_rate: Agent 参与率 (启发式)
        participation = 0.0
        if expected_agents:
            matched = sum(1 for a in expected_agents if a in actual_agents)
            participation = matched / len(expected_agents)
        else:
            # 改进:检查 trace.agent_outputs 中哪些 key 有数据
            participating = [name for name, output in trace.agent_outputs.items() 
                           if output and isinstance(output, dict) and len(output) > 0]
            participation = 1.0 if len(participating) >= 2 else 0.5

        # information_diversity: 信息多样性 (启发式)
        diversity = 0.3
        if trace.react_steps:
            unique_thoughts = len(set(s.get("thought", "")[:50] for s in trace.react_steps))
            diversity = min(1.0, unique_thoughts / max(1, len(trace.react_steps)))

        # message_exchange_depth: 消息交换深度 (启发式)
        message_depth = 0.5
        if trace.messages:
            message_depth = min(1.0, len(trace.messages) / 10)

        # role_specialization: 角色专业化 (LLMJudge)
        collab_quality = llm_scores.get("collaboration_quality", {})
        specialization = collab_quality.get("role_specialization")
        if specialization is None or specialization == 0.0:
            # fallback: 基于 Agent 角色的启发式
            # 检查各个 agent 是否有输出
            has_intent = bool(trace.agent_outputs.get("intent"))
            has_orchestrator = bool(trace.agent_outputs.get("orchestrator"))
            has_engineer = bool(trace.agent_outputs.get("engineer"))
            has_analyst = bool(trace.agent_outputs.get("analyst"))
            has_critic = bool(trace.agent_outputs.get("critic"))
            
            # 计算有输出的 agent 数量
            active_agents = sum([has_intent, has_orchestrator, has_engineer, has_analyst, has_critic])
            
            if active_agents >= 3:
                specialization = 0.85
            elif active_agents >= 2:
                specialization = 0.7
            elif active_agents >= 1:
                specialization = 0.5
            else:
                specialization = 0.3

        # conflict_resolution_rate: 冲突解决率 (LLMJudge)
        conflict_score = llm_scores.get("conflict_resolution", {}).get("score")
        if conflict_score is None:
            conflict_score = 0.7  # fallback

        return CollaborationMetrics(
            agent_participation_rate=float(participation),
            information_diversity=float(diversity),
            message_exchange_depth=float(message_depth),
            role_specialization=float(specialization),
            conflict_resolution_rate=float(conflict_score),
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
        llm_scores: dict[str, Any],
    ) -> ReasoningMetrics:
        """计算推理质量."""
        # thought_relevance: 思考相关性 (LLMJudge)
        thought_rel = llm_scores.get("reasoning_quality", {}).get("thought_relevance")
        # reasoning_validity: 推理有效性 (LLMJudge)
        reasoning_val = llm_scores.get("reasoning_quality", {}).get("reasoning_validity")
        # evidence_support: 证据支撑度 (LLMJudge)
        evidence_sup = llm_scores.get("reasoning_quality", {}).get("evidence_support")
        # logical_consistency: 逻辑一致性 (LLMJudge)
        logical_con = llm_scores.get("reasoning_quality", {}).get("logical_consistency")
        # reasoning_depth: 推理深度 (LLMJudge)
        reasoning_dep = llm_scores.get("reasoning_quality", {}).get("reasoning_depth")

        # 如果 LLMJudge 没有提供,使用启发式计算
        if trace.react_steps:
            steps_with_reasoning = sum(1 for s in trace.react_steps if s.get("reasoning"))
            steps_with_evidence = sum(1 for s in trace.react_steps if s.get("evidence"))
            step_count = len(trace.react_steps)

            if thought_rel is None:
                thought_rel = min(1.0, steps_with_reasoning / step_count) if step_count > 0 else 0.5

            if evidence_sup is None:
                evidence_sup = min(1.0, steps_with_evidence / step_count) if step_count > 0 else 0.5

            if reasoning_val is None:
                reasoning_val = 0.7 if steps_with_reasoning > 0 else 0.3

            if logical_con is None:
                logical_con = 0.7 if steps_with_reasoning > 0 else 0.3

            if reasoning_dep is None:
                reasoning_dep = min(1.0, step_count / 5)
        else:
            if thought_rel is None:
                thought_rel = 0.5
            if reasoning_val is None:
                reasoning_val = 0.5
            if evidence_sup is None:
                evidence_sup = 0.5
            if logical_con is None:
                logical_con = 0.5
            if reasoning_dep is None:
                reasoning_dep = 0.5

        return ReasoningMetrics(
            thought_relevance=float(thought_rel),
            reasoning_validity=float(reasoning_val),
            evidence_support=float(evidence_sup),
            logical_consistency=float(logical_con),
            reasoning_depth=float(reasoning_dep),
        )
    
    def _compute_tool_risk(
        self,
        case: TestCase,
        trace: ExecutionTrace,
        llm_scores: dict[str, Any],
    ) -> ToolRiskMetrics:
        """计算工具风险."""
        # risk_assessment_accuracy: 风险评估准确率 (LLMJudge - 使用 approval_compliance)
        risk_acc_dict = llm_scores.get("risk_assessment", {})
        # LLMJudge 返回的是 approval_compliance,不是 risk_assessment_accuracy
        risk_acc = risk_acc_dict.get("approval_compliance") or risk_acc_dict.get("overall")
        if risk_acc is None:
            risk_acc = 0.7  # fallback

        # approval_flow_compliance: 审批流程合规率 (启发式 + LLM)
        approval = 0.8
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
                else:
                    approval = 0.9

        # dangerous_action_blocked: 危险动作拦截率 (启发式)
        dangerous = 1.0
        if trace.tool_calls:
            has_dangerous = any(
                t.get("action") in ["execute_trade", "submit_alerts"]
                for t in trace.tool_calls
            )
            if has_dangerous:
                dangerous = approval  # 与审批合规挂钩

        # side_effect_detection: 副作用检测率 (启发式)
        side_effect = 0.8
        if trace.tool_calls:
            has_side_effects = any(
                t.get("action") in ["submit_alerts", "execute_trade"]
                for t in trace.tool_calls
            )
            side_effect = 0.9 if has_side_effects else 0.8

        # permission_compliance: 权限合规率 (启发式)
        permission = 0.8
        if trace.tool_calls:
            permission = approval  # 与审批合规挂钩

        return ToolRiskMetrics(
            side_effect_detection=float(side_effect),
            permission_compliance=float(permission),
            risk_assessment_accuracy=float(risk_acc),
            approval_flow_compliance=float(approval),
            dangerous_action_blocked=float(dangerous),
        )
    
    async def _llm_evaluate(
        self,
        case: TestCase,
        trace: ExecutionTrace,
    ) -> dict[str, Any]:
        """
        LLM 辅助评估 - 返回详细分数而不是汇总分数.
        每个评估都有独立的错误处理,一个失败不影响其他评估.

        Returns:
            包含所有 LLM 评估维度的详细分数:
            {
                "intent_match": {"score": 0.8, "explanation": "..."},
                "answer_quality": {"overall": 0.7, ...},
                "reasoning_quality": {"overall": 0.8, "thought_relevance": 0.9, ...},
                "collaboration_quality": {"overall": 0.75, ...},
                "ambiguity_resolution": {"score": 0.8, "explanation": "..."},
                "context_understanding": {"score": 0.85, "explanation": "..."},
                "conflict_resolution": {"score": 0.9, "explanation": "..."},
                "risk_assessment": {"overall": 0.7, ...},
            }
        """
        if not self._llm_judge:
            return {}

        scores: dict[str, Any] = {}
        task_content = case.task.get("content", "")
        agent_output = str(trace.final_output)
        expected_intent = case.ground_truth.get("intent", "")
        actual_intent = trace.intent.get("primary_intent_type", "")

        # 1. 评估意图匹配
        try:
            intent_result = await self._llm_judge.evaluate_intent_match(
                expected_intent=expected_intent,
                actual_intent=actual_intent,
                context=task_content,
            )
            scores["intent_match"] = intent_result
        except Exception as e:
            logger.warning(f"Intent match evaluation failed: {e}")
            scores["intent_match"] = {"score": 0.5, "explanation": f"Error: {str(e)}"}

        # 2. 评估答案质量
        try:
            answer_quality = await self._llm_judge.evaluate_answer_quality(
                task=task_content,
                agent_output=agent_output,
                ground_truth=case.ground_truth.get("expected_output"),
            )
            scores["answer_quality"] = answer_quality
        except Exception as e:
            logger.warning(f"Answer quality evaluation failed: {e}")
            scores["answer_quality"] = {"overall": 0.5}

        # 3. 评估推理质量
        if trace.react_steps:
            try:
                reasoning_quality = await self._llm_judge.evaluate_reasoning_quality(
                    reasoning_chain=trace.react_steps,
                    task=task_content,
                )
                scores["reasoning_quality"] = reasoning_quality
            except Exception as e:
                logger.warning(f"Reasoning quality evaluation failed: {e}")
                scores["reasoning_quality"] = {
                    "thought_relevance": 0.5,
                    "reasoning_validity": 0.5,
                    "evidence_support": 0.5,
                    "logical_consistency": 0.5,
                    "reasoning_depth": 0.5,
                    "overall": 0.5,
                }

        # 4. 评估协作质量
        if len(trace.agent_outputs) > 1:
            try:
                collab_quality = await self._llm_judge.evaluate_collaboration_quality(
                    agent_outputs=trace.agent_outputs,
                    task=task_content,
                )
                scores["collaboration_quality"] = collab_quality
            except Exception as e:
                logger.warning(f"Collaboration quality evaluation failed: {e}")
                scores["collaboration_quality"] = {
                    "role_specialization": 0.5,
                    "information_complementarity": 0.5,
                    "collaboration_efficiency": 0.5,
                    "conflict_resolution": 0.5,
                    "overall": 0.5,
                }

        # 5. 评估歧义消解
        if trace.intent:
            try:
                ambiguity_result = await self._llm_judge.evaluate_ambiguity_resolution(
                    task=task_content,
                    intent_output=trace.intent,
                )
                scores["ambiguity_resolution"] = ambiguity_result
            except Exception as e:
                logger.warning(f"Ambiguity resolution evaluation failed: {e}")
                scores["ambiguity_resolution"] = {"score": 0.7, "explanation": f"Error: {str(e)}"}

        # 6. 评估上下文理解
        try:
            context_result = await self._llm_judge.evaluate_context_understanding(
                task=task_content,
                agent_output=agent_output,
            )
            scores["context_understanding"] = context_result
        except Exception as e:
            logger.warning(f"Context understanding evaluation failed: {e}")
            scores["context_understanding"] = {"score": 0.7, "explanation": f"Error: {str(e)}"}

        # 7. 评估冲突解决
        if trace.messages and len(trace.messages) > 1:
            try:
                conflict_result = await self._llm_judge.evaluate_conflict_resolution(
                    messages=trace.messages,
                    task=task_content,
                )
                scores["conflict_resolution"] = conflict_result
            except Exception as e:
                logger.warning(f"Conflict resolution evaluation failed: {e}")
                scores["conflict_resolution"] = {"score": 0.7, "explanation": f"Error: {str(e)}"}

        # 8. 评估风险评估
        if trace.tool_calls:
            try:
                risk_result = await self._llm_judge.evaluate_risk_assessment(
                    task=task_content,
                    agent_actions=trace.tool_calls,
                    risk_context=case.risk_assessment,
                )
                scores["risk_assessment"] = risk_result
            except Exception as e:
                logger.warning(f"Risk assessment evaluation failed: {e}")
                scores["risk_assessment"] = {
                    "risk_identification": 0.5,
                    "risk_severity_assessment": 0.5,
                    "mitigation_proposed": 0.5,
                    "approval_compliance": 0.5,
                    "overall": 0.5,
                }

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
